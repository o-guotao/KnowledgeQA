import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_hash: str | None
    folder: str = ""
    tags: list = []
    status: str
    chunk_size: int
    chunk_overlap: int
    chunk_count: int
    error: str | None
    version: int = 1
    ingested_at: datetime | None = None
    # 失效检测：非 ORM 列，由 API 层按「文档签名 vs 当前 settings」计算后填入
    stale: bool = False
    stale_reasons: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContentUpdateResult(BaseModel):
    """就地更新响应：updated=false 表示内容 hash 未变（幂等 no-op）。"""

    updated: bool
    document: DocumentOut


class DocumentUpdate(BaseModel):
    folder: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = None


class BatchDeleteRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class BatchDeleteResponse(BaseModel):
    deleted: int
    failed: list[uuid.UUID] = []


class ChunkOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    content: str
    start_offset: int
    end_offset: int
    total_chunks: int
