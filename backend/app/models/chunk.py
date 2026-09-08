import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base
from app.storage_compat import UUIDType, get_vector_type


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # 冗余 user_id 便于按权限过滤召回
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, default=0)
    # 父子块：指向父块 id，召回小块后取父块上下文注入 prompt
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # 块类型：child（小块，用于 embedding 召回）| parent（大块，提供上下文）
    block_type: Mapped[str] = mapped_column(String(16), default="child")
    # pgvector 模式为 Vector(N)，sqlite 模式为 JSON（list[float]）
    embedding: Mapped[list[float]] = mapped_column(get_vector_type(get_settings().embedding_dim))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
