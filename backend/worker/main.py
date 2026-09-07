"""任务 worker：轮询 tasks 表，抢占执行，超时/指数退避重试/超限进死信。

状态机：pending -> running -> done
                         +-> failed(可重试，next_run_at = now + base*2^n) -> dead(超过 max_retries)
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text, update

from app.config import get_settings
from app.db import SessionLocal
from app.logging_config import configure_logging, set_trace_id
from app.models.document import Document
from app.models.task import Task

logger = logging.getLogger("worker")


async def reap_stuck_running(settings) -> int:
    """回收卡死的 running 任务：started_at 早于 timeout 的判为僵尸，
    重置为 failed 交由退避重试/死信流程处理。覆盖 worker 崩溃/OOM/断电场景。"""
    async with SessionLocal() as db:
        result = await db.execute(
            text(
                """
                UPDATE tasks SET status = 'failed', error = left(error || ' | ', 500) || 'reaped: stuck running'
                WHERE status = 'running'
                  AND started_at < now() - make_interval(secs => :timeout)
                """
            ),
            {"timeout": settings.task_timeout_seconds * 2},
        )
        if result.rowcount:
            await db.commit()
            logger.warning(
                "reaped stuck running tasks",
                extra={"event": "task_reaped", "extra": {"count": result.rowcount}},
            )
        return result.rowcount or 0


async def claim_task() -> Task | None:
    """FOR UPDATE SKIP LOCKED 抢占一条到期任务，避免多 worker 重复执行。"""
    async with SessionLocal() as db:
        row = (
            await db.execute(
                text(
                    """
                    UPDATE tasks SET status = 'running', started_at = now()
                    WHERE id = (
                        SELECT id FROM tasks
                        WHERE status IN ('pending', 'failed') AND next_run_at <= now()
                        ORDER BY next_run_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING id
                    """
                )
            )
        ).first()
        await db.commit()
        if row is None:
            return None
    async with SessionLocal() as db:
        return await db.get(Task, row[0])


async def ingest_document(document_id: uuid.UUID) -> None:
    """切分 + embedding + 入库，chunk 写入以 document_id 事务包裹保证一致性。"""
    from app.models.chunk import Chunk
    from app.services.chunking import extract_text, split_text
    from app.services.embedding import embed_texts
    from app.services.storage import get_object

    async with SessionLocal() as db:
        document = await db.get(Document, document_id)
        if document is None:
            raise RuntimeError(f"文档不存在：{document_id}")
        document.status = "processing"
        await db.commit()

        data = await get_object(document.object_key)
        text_content = extract_text(document.filename, data)
        if not text_content:
            raise RuntimeError("文档提取后无文本内容")
        pieces = split_text(text_content, document.chunk_size, document.chunk_overlap)
        logger.info(
            "document split",
            extra={"document_id": str(document_id), "extra": {"chunks": len(pieces),
                   "chunk_size": document.chunk_size, "overlap": document.chunk_overlap}},
        )
        vectors = await embed_texts([p.content for p in pieces])

        await db.execute(
            text("DELETE FROM chunks WHERE document_id = :did"), {"did": document_id}
        )
        for piece, vector in zip(pieces, vectors, strict=True):
            db.add(Chunk(
                document_id=document.id, user_id=document.user_id,
                chunk_index=piece.chunk_index, content=piece.content,
                start_offset=piece.start_offset, end_offset=piece.end_offset,
                embedding=vector,
            ))
        document.status = "ready"
        document.chunk_count = len(pieces)
        document.error = None
        await db.commit()


async def mark_document_failed(document_id: uuid.UUID, error: str) -> None:
    try:
        async with SessionLocal() as db:
            await db.execute(
                update(Document).where(Document.id == document_id).values(status="failed", error=error[:500])
            )
            await db.commit()
    except Exception:
        logger.exception("failed to mark document failed")


async def run_task(task: Task) -> None:
    if task.type == "ingest_document":
        await ingest_document(uuid.UUID(task.payload["document_id"]))
    elif task.type == "demo_fail":
        # 演示用：恒超时，用于验证"超时 -> 重试 -> 死信"链路
        await asyncio.sleep(1e6)
    else:
        raise RuntimeError(f"未知任务类型：{task.type}")


async def handle_failure(task: Task, error: str) -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        row = await db.get(Task, task.id)
        if row is None:
            return
        row.error = error[:500]
        row.finished_at = datetime.now(timezone.utc)
        if row.retry_count < row.max_retries:
            row.retry_count += 1
            row.status = "failed"
            backoff = settings.task_retry_base_seconds * (2 ** (row.retry_count - 1))
            row.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            logger.warning(
                "task failed, will retry",
                extra={"task_id": str(row.id), "extra": {"retry": row.retry_count, "backoff_s": backoff}},
            )
        else:
            row.status = "dead"
            logger.error(
                "task moved to dead letter",
                extra={"task_id": str(row.id), "event": "task_dead"},
            )
        await db.commit()


async def loop() -> None:
    settings = get_settings()
    logger.info("worker started")
    reap_counter = 0
    while True:
        # 每约 60s 巡检一次僵尸 running，避免高频查询
        reap_counter += 1
        if reap_counter % 30 == 1:
            await reap_stuck_running(settings)
        task = await claim_task()
        if task is None:
            await asyncio.sleep(2)
            continue
        set_trace_id(task.trace_id or uuid.uuid4().hex[:16])
        started = time.monotonic()
        logger.info("task claimed", extra={"task_id": str(task.id), "extra": {"type": task.type}})
        try:
            await asyncio.wait_for(run_task(task), timeout=settings.task_timeout_seconds)
        except asyncio.TimeoutError:
            await handle_failure(task, f"任务超时（>{settings.task_timeout_seconds}s）")
            if task.type == "ingest_document":
                await mark_document_failed(uuid.UUID(task.payload["document_id"]), "处理超时")
            continue
        except Exception as exc:
            logger.exception("task execution error", extra={"task_id": str(task.id)})
            await handle_failure(task, f"{type(exc).__name__}: {exc}")
            if task.type == "ingest_document":
                await mark_document_failed(uuid.UUID(task.payload["document_id"]), str(exc)[:300])
            continue

        duration_ms = round((time.monotonic() - started) * 1000, 1)
        async with SessionLocal() as db:
            await db.execute(
                update(Task)
                .where(Task.id == task.id)
                .values(status="done", finished_at=datetime.now(timezone.utc), duration_ms=duration_ms)
            )
            await db.commit()
        logger.info("task done", extra={"task_id": str(task.id), "extra": {"duration_ms": duration_ms}})


async def _verify_embedding_on_start(settings) -> None:
    """worker 启动校验 embedding：worker 是实际执行 embedding 的进程，
    生产环境后端不可用必须 fail fast，否则切分任务全部失败进死信。"""
    from app.services.embeddings import verify_embedding_ready

    ok, message = await verify_embedding_ready()
    if not ok:
        if settings.environment == "production":
            raise RuntimeError(f"worker embedding 生产启动校验失败：{message}")
        logger.warning("embedding startup check failed (dev, continuing): %s", message)
    else:
        logger.info("worker startup check: %s", message)


def main() -> None:
    configure_logging()
    settings = get_settings()
    asyncio.run(_verify_embedding_on_start(settings))
    asyncio.run(loop())


if __name__ == "__main__":
    main()
