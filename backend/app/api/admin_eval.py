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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.security import require_admin
from app.db import get_db
from app.logging_config import get_trace_id
from app.models.eval import EvalDataset, EvalRun, EvalRunItem
from app.models.message import Message
from app.models.task import Task
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.schemas.eval import (
    BuiltinImportRequest,
    EvalDatasetOut,
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


@router.get("/admin/eval/datasets", response_model=list[EvalDatasetOut])
async def list_datasets(db: AsyncSession = Depends(get_db)) -> list[EvalDatasetOut]:
    rows = (await db.execute(select(EvalDataset).order_by(EvalDataset.created_at.desc()))).scalars().all()
    return [_dataset_out(d) for d in rows]


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


@router.get("/admin/eval/runs", response_model=list[EvalRunOut])
async def list_runs(
    dataset_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[EvalRunOut]:
    stmt = select(EvalRun).order_by(EvalRun.created_at.desc()).limit(100)
    if dataset_id is not None:
        stmt = stmt.where(EvalRun.dataset_id == dataset_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [EvalRunOut.model_validate(r) for r in rows]


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
