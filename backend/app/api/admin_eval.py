"""评测中心：数据集管理 / 评测运行 / 线上耗时统计。全部端点要求 admin。

执行模型：发起 run → eval_runs(pending) + tasks(run_eval) 入队 → worker 异步执行
（独立临时库，见 services/eval_runner.py）→ 页面轮询状态。同一时刻仅允许一个在途 run。
"""
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import (
    LIKE_ESCAPE,
    PageParams,
    like_pattern,
    make_page,
    normalize_q,
    paginate,
)
from app.core.security import require_admin
from app.db import get_db
from app.logging_config import get_trace_id
from app.models.eval import EvalDataset, EvalRun, EvalRunItem
from app.models.message import Message
from app.models.task import Task
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.schemas.common import Page
from app.schemas.eval import (
    BuiltinImportRequest,
    EvalDatasetOut,
    EvalRunBatchDeleteRequest,
    EvalRunBatchDeleteResponse,
    EvalRunCreate,
    EvalRunDetail,
    EvalRunItemOut,
    EvalRunOut,
    OnlinePoint,
    OnlineStatsOut,
)
from app.services.eval_runner import ALL_GROUPS, parse_dataset

router = APIRouter(dependencies=[Depends(require_admin)])

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
MAX_DATASET_BYTES = 1 * 1024 * 1024  # 1MB


def _dataset_out(d: EvalDataset) -> EvalDatasetOut:
    return EvalDatasetOut.model_validate(d)


@router.get("/admin/eval/datasets", response_model=Page[EvalDatasetOut])
async def list_datasets(
    q: str | None = None,
    source: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[EvalDatasetOut]:
    """评测数据集列表：q 匹配名称，可按 source（builtin/upload）过滤，服务端分页。"""
    stmt = select(EvalDataset)
    term = normalize_q(q)
    if term is not None:
        stmt = stmt.where(EvalDataset.name.ilike(like_pattern(term), escape=LIKE_ESCAPE))
    if source is not None:
        stmt = stmt.where(EvalDataset.source == source)
    stmt = stmt.order_by(EvalDataset.created_at.desc(), EvalDataset.id.desc())
    rows, total = await paginate(db, stmt, params)
    return make_page([_dataset_out(row[0]) for row in rows], total, params)


@router.post("/admin/eval/datasets/import-builtin", response_model=EvalDatasetOut, status_code=201)
async def import_builtin(body: BuiltinImportRequest, db: AsyncSession = Depends(get_db)) -> EvalDatasetOut:
    """内置样例问句集一键导入（eval/questions.jsonl / questions_hard.jsonl）。"""
    path = BASE_DIR / "eval" / body.file
    if not path.exists():
        raise not_found("内置问句集")
    payload = path.read_text(encoding="utf-8")
    try:
        items = parse_dataset(payload)
    except ValueError as exc:
        raise AppError("BAD_DATASET", f"内置问句集解析失败：{exc}", 500)
    name = {"questions.jsonl": "内置样例（30 题）", "questions_hard.jsonl": "内置难句集"}.get(body.file, body.file)
    # 同名内置集重复导入 → 更新而不是堆副本
    existing = (
        await db.execute(select(EvalDataset).where(EvalDataset.name == name, EvalDataset.source == "builtin"))
    ).scalar_one_or_none()
    if existing is not None:
        existing.payload = payload
        existing.item_count = len(items)
        await db.commit()
        await db.refresh(existing)
        return _dataset_out(existing)
    dataset = EvalDataset(name=name, source="builtin", item_count=len(items), payload=payload)
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return _dataset_out(dataset)


@router.post("/admin/eval/datasets", response_model=EvalDatasetOut, status_code=201)
async def upload_dataset(file: UploadFile, db: AsyncSession = Depends(get_db)) -> EvalDatasetOut:
    """上传问句集 jsonl（≤1MB，≤500 条，逐行校验 q/gold_doc）。"""
    data = await file.read()
    if not data:
        raise AppError("EMPTY_FILE", "文件内容为空", 400)
    if len(data) > MAX_DATASET_BYTES:
        raise AppError("FILE_TOO_LARGE", "数据集文件超过 1MB 限制", 413)
    try:
        payload = data.decode("utf-8")
    except UnicodeDecodeError:
        raise AppError("BAD_DATASET", "文件必须是 UTF-8 编码的 jsonl", 400)
    try:
        items = parse_dataset(payload)
    except ValueError as exc:
        raise AppError("BAD_DATASET", str(exc), 400)
    name = (file.filename or "未命名数据集")[:128]
    dataset = EvalDataset(name=name, source="upload", item_count=len(items), payload=payload)
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return _dataset_out(dataset)


@router.delete("/admin/eval/datasets/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    dataset = await db.get(EvalDataset, dataset_id)
    if dataset is None:
        raise not_found("数据集")
    await db.delete(dataset)  # 关联 runs 的 dataset_id 置 NULL（ondelete=SET NULL），历史保留
    await db.commit()


@router.get("/admin/eval/runs", response_model=Page[EvalRunOut])
async def list_runs(
    q: str | None = None,
    dataset_id: uuid.UUID | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[EvalRunOut]:
    """评测运行列表：q 匹配运行名，可按 dataset_id / status 过滤，服务端分页。

    改造前硬编码 .limit(100) 会静默截断历史记录，现由 page_size 控制（可翻到全部历史）。
    """
    stmt = select(EvalRun)
    term = normalize_q(q)
    if term is not None:
        stmt = stmt.where(EvalRun.name.ilike(like_pattern(term), escape=LIKE_ESCAPE))
    if dataset_id is not None:
        stmt = stmt.where(EvalRun.dataset_id == dataset_id)
    if status is not None:
        stmt = stmt.where(EvalRun.status == status)
    stmt = stmt.order_by(EvalRun.created_at.desc(), EvalRun.id.desc())
    rows, total = await paginate(db, stmt, params)
    return make_page([EvalRunOut.model_validate(row[0]) for row in rows], total, params)


@router.post("/admin/eval/runs", response_model=EvalRunOut, status_code=202)
async def create_run(
    body: EvalRunCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> EvalRunOut:
    """发起评测：eval_runs(pending) + run_eval 任务入队。并发闸：已有在途 run → 409。"""
    dataset = await db.get(EvalDataset, body.dataset_id)
    if dataset is None:
        raise not_found("数据集")
    busy = (
        await db.execute(
            select(func.count()).select_from(EvalRun).where(EvalRun.status.in_(("pending", "running")))
        )
    ).scalar_one()
    if busy:
        raise AppError("EVAL_RUN_BUSY", "已有评测正在运行，请等待完成后再发起", 409)

    config = {
        "groups": body.groups or ALL_GROUPS,
        "top_k_max": body.top_k_max,
        "with_llm": body.with_llm,
        "chunk_size": body.chunk_size,
        "chunk_overlap": body.chunk_overlap,
        "kb_mode": body.kb_mode,
        # with_llm 的 provider 解析与 online 语料检索范围都用创建者身份
        "user_id": str(user.id),
    }
    run = EvalRun(
        dataset_id=dataset.id,
        name=body.name or f"{dataset.name} · {datetime.now(timezone.utc).strftime('%m-%d %H:%M')}",
        config=config,
        status="pending",
    )
    db.add(run)
    await db.flush()
    db.add(Task(
        type="run_eval",
        payload={"run_id": str(run.id)},
        user_id=user.id,
        trace_id=get_trace_id(),
        max_retries=0,  # 评测失败不重试：结果落 eval_runs.error，人工重发
    ))
    await db.commit()
    await db.refresh(run)
    return EvalRunOut.model_validate(run)


async def _delete_run_and_tasks(db: AsyncSession, run: EvalRun) -> None:
    """删除 run + 逐题明细（显式删除：sqlite 默认不强制 FK CASCADE）+ 尽力取消其未完成任务。"""
    await db.execute(delete(EvalRunItem).where(EvalRunItem.run_id == run.id))
    stale = (
        await db.execute(
            select(Task).where(
                Task.type == "run_eval",
                Task.status.in_(("pending", "failed", "dead")),
            )
        )
    ).scalars().all()
    for task in stale:
        if (task.payload or {}).get("run_id") == str(run.id):
            await db.delete(task)
    await db.delete(run)


@router.delete("/admin/eval/runs/{run_id}", status_code=204)
async def delete_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise not_found("评测运行")
    await _delete_run_and_tasks(db, run)
    await db.commit()


@router.post("/admin/eval/runs/batch-delete", response_model=EvalRunBatchDeleteResponse)
async def batch_delete_runs(
    body: EvalRunBatchDeleteRequest, db: AsyncSession = Depends(get_db)
) -> EvalRunBatchDeleteResponse:
    """批量删除评测运行：逐个删除（含逐题明细级联），失败的收集返回。"""
    deleted = 0
    failed: list[uuid.UUID] = []
    for run_id in body.run_ids:
        run = await db.get(EvalRun, run_id)
        if run is None:
            failed.append(run_id)
            continue
        await _delete_run_and_tasks(db, run)
        deleted += 1
    await db.commit()
    return EvalRunBatchDeleteResponse(deleted=deleted, failed=failed)


@router.get("/admin/eval/runs/{run_id}", response_model=EvalRunDetail)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> EvalRunDetail:
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise not_found("评测运行")
    items = (
        await db.execute(select(EvalRunItem).where(EvalRunItem.run_id == run_id).order_by(EvalRunItem.idx))
    ).scalars().all()
    return EvalRunDetail(
        run=EvalRunOut.model_validate(run),
        items=[EvalRunItemOut.model_validate(it) for it in items],
    )


@router.get("/admin/eval/runs/{run_id}/items.csv")
async def export_run_csv(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Response:
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise not_found("评测运行")
    items = (
        await db.execute(select(EvalRunItem).where(EvalRunItem.run_id == run_id).order_by(EvalRunItem.idx))
    ).scalars().all()
    groups = list((run.summary or {}).keys())
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["idx", "question", "gold_doc"]
    for g in groups:
        header += [f"{g}_rank", f"{g}_hit"]
    writer.writerow(header)
    for it in items:
        row = [it.idx, it.question, it.gold_doc]
        for g in groups:
            r = (it.ranks or {}).get(g, {})
            row += [r.get("rank", 0), int(bool(r.get("hit")))]
        writer.writerow(row)
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="eval_run_{run_id.hex[:8]}.csv"'},
    )


def _percentile(sorted_vals: list[float], pct: float) -> float | None:
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, round(pct * (len(sorted_vals) - 1))))
    return round(sorted_vals[k], 1)


@router.get("/admin/eval/online-stats", response_model=OnlineStatsOut)
async def online_stats(days: int = Query(14, ge=1, le=90), db: AsyncSession = Depends(get_db)) -> OnlineStatsOut:
    """线上质量：usage_records 按日 p50/p95（方言无关，Python 端聚合）+ 点踩率。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(UsageRecord.created_at, UsageRecord.total_ms, UsageRecord.ttft_ms,
                   UsageRecord.recall_ms, UsageRecord.rerank_ms)
            .where(UsageRecord.created_at >= since, UsageRecord.total_ms.is_not(None))
        )
    ).all()
    by_date: dict[str, dict[str, list]] = {}
    for created_at, total_ms, ttft_ms, recall_ms, rerank_ms in rows:
        d = created_at.date().isoformat()
        bucket = by_date.setdefault(d, {"total": [], "ttft": [], "recall": [], "rerank": []})
        bucket["total"].append(float(total_ms))
        if ttft_ms is not None:
            bucket["ttft"].append(float(ttft_ms))
        if recall_ms is not None:
            bucket["recall"].append(float(recall_ms))
        if rerank_ms is not None:
            bucket["rerank"].append(float(rerank_ms))
    points = [
        OnlinePoint(
            date=d,
            calls=len(b["total"]),
            p50_total_ms=_percentile(sorted(b["total"]), 0.5),
            p95_total_ms=_percentile(sorted(b["total"]), 0.95),
            p50_ttft_ms=_percentile(sorted(b["ttft"]), 0.5),
            avg_recall_ms=round(sum(b["recall"]) / len(b["recall"]), 1) if b["recall"] else None,
            avg_rerank_ms=round(sum(b["rerank"]) / len(b["rerank"]), 1) if b["rerank"] else None,
        )
        for d, b in sorted(by_date.items())
    ]

    up = (
        await db.execute(
            select(func.count()).select_from(Message)
            .where(Message.role == "assistant", Message.feedback == "up", Message.created_at >= since)
        )
    ).scalar_one()
    down = (
        await db.execute(
            select(func.count()).select_from(Message)
            .where(Message.role == "assistant", Message.feedback == "down", Message.created_at >= since)
        )
    ).scalar_one()
    down_rate = round(down / (up + down), 4) if (up + down) else None
    return OnlineStatsOut(days=days, points=points, feedback_up=up, feedback_down=down, down_rate=down_rate)
