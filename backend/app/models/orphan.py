import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.storage_compat import UUIDType


class StorageOrphan(Base):
    """对象存储孤儿记录：DB 已删但对象存储删除失败的对象 key，便于定期清理。"""
    __tablename__ = "storage_orphans"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    object_key: Mapped[str] = mapped_column(String(512), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
