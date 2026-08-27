import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    chunk_size: int
    chunk_overlap: int
    chunk_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChunkOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    content: str
    start_offset: int
    end_offset: int
    total_chunks: int
