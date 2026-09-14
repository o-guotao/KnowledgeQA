"""评测中心数据模型：数据集 / 评测运行 / 逐题明细。

- eval_datasets：问句集版本化（builtin 导入或上传，payload 存 jsonl 原文）
- eval_runs：一次评测运行（配置快照 + 状态 + 汇总指标），经 tasks 表由 worker 异步执行
- eval_run_items：逐题 × 各配置组的排名/命中/分阶段耗时明细
"""
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.storage_compat import UUIDType

# eval_runs.status 状态机：pending -> running -> done | failed
EVAL_RUN_STATUSES = ("pending", "running", "done", "failed")


class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16), default="upload")  # builtin | upload
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    # 问句集 jsonl 原文（每行 {"q","gold_doc","gold_keywords"?}），≤1MB 由 API 校验
    payload: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_status_created", "status", "created_at"),
        Index("ix_eval_runs_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(), ForeignKey("eval_datasets.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), default="")
    # 配置快照：{groups:[...], top_k_max, with_llm, chunk_size, chunk_overlap, embedding_backend, embedding_model}
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # 汇总：{"<group>": {"recall_at_k": {"1":..,"5":..}, "mrr": .., "answer_hit_rate"?: ..,
    #                   "latency_ms": {"embed_avg":..,"recall_avg":..,"rerank_avg":..,"llm_avg"?:..}}}
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvalRunItem(Base):
    __tablename__ = "eval_run_items"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer)  # 题号（1-based）
    question: Mapped[str] = mapped_column(Text)
    gold_doc: Mapped[str] = mapped_column(String(256))
    # {"<group>": {"rank": int, "hit": bool, "cited": [..], "answer_hit"?: bool,
    #              "injection_blocked"?: bool, "latency_ms": {...}}}
    ranks: Mapped[dict] = mapped_column(JSON, default=dict)
