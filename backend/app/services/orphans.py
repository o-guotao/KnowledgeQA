"""对象存储孤儿记录的辅助函数。模型定义在 app.models.orphan。"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orphan import StorageOrphan


async def record_orphan(db: AsyncSession, object_key: str, reason: str) -> None:
    """记录孤儿对象。db 为当前事务中的 AsyncSession，与本操作同事务提交。"""
    db.add(StorageOrphan(object_key=object_key, reason=reason[:200]))
    await db.flush()
