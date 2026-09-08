"""每次 LLM 调用明细：管理后台用量看板 / 成本报表的数据源。

与 quotas（月度配额累计，管限额）并存：本表按调用逐行记录，管统计与报表。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.storage_compat import UUIDType


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_records_user_created", "user_id", "created_at"),
        Index("ix_usage_records_created", "created_at"),
        Index("ix_usage_records_model", "model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType(), nullable=True)
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cny: Mapped[float] = mapped_column(Float, default=0.0)
    trace_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
