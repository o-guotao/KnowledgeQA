"""对象存储孤儿记录：DB 已删但 MinIO 删除失败的对象 key，便于定期清理。

最终一致策略：删除是跨 DB 与对象存储的复合操作，无法两阶段提交；
接受 DB 删除成功而对象存储失败的情况，但把孤儿 key 落表以便审计与清理。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StorageOrphan(Base):
    __tablename__ = "storage_orphans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    object_key: Mapped[str] = mapped_column(String(512), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


async def record_orphan(db, object_key: str, reason: str) -> None:
    """记录孤儿对象。db 为当前事务中的 AsyncSession，与本操作同事务提交。"""
    db.add(StorageOrphan(object_key=object_key, reason=reason[:200]))
    await db.flush()
