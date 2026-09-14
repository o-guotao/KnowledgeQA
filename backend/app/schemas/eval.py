import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EvalDatasetOut(BaseModel):
    id: uuid.UUID
    name: str
    source: str
    item_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BuiltinImportRequest(BaseModel):
    file: str = Field(pattern="^(questions|questions_hard)\\.jsonl$")


class EvalRunCreate(BaseModel):
    dataset_id: uuid.UUID
    name: str = Field(default="", max_length=128)
    groups: list[str] | None = None  # None=全部四组
    top_k_max: int = Field(default=10, ge=1, le=20)
    with_llm: bool = False
    chunk_size: int = Field(default=128, ge=32, le=2048)
    chunk_overlap: int = Field(default=32, ge=0, le=512)


class EvalRunOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID | None
    name: str
    config: dict
    status: str
    summary: dict
    error: str | None
    duration_ms: float | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class EvalRunItemOut(BaseModel):
    id: uuid.UUID
    idx: int
    question: str
    gold_doc: str
    ranks: dict

    model_config = {"from_attributes": True}


class EvalRunDetail(BaseModel):
    run: EvalRunOut
    items: list[EvalRunItemOut]


class OnlinePoint(BaseModel):
    date: str
    calls: int
    p50_total_ms: float | None
    p95_total_ms: float | None
    p50_ttft_ms: float | None
    avg_recall_ms: float | None
    avg_rerank_ms: float | None


class OnlineStatsOut(BaseModel):
    days: int
    points: list[OnlinePoint]
    feedback_up: int
    feedback_down: int
    down_rate: float | None
