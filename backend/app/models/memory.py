"""长期记忆条目（L3）：从对话中沉淀的用户事实/偏好，跨会话可检索。

与文档 chunk 的关系：同为“可检索知识”，但来源是对话而非上传文档；
单独建表而非塞进 documents/chunks，因为：
- 生命周期不同（可单条删除/过期，无 object_key/version）
- 召回时需与文档召回独立限额（记忆召回 top 小份额）
- 避免污染文档管理页/统计口径
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.db import Base
from app.storage_compat import UUIDType, get_vector_type


class MemoryItem(Base):
    __tablename__ = "memory_items"
    # 同一用户同 key 的最新值唯一（覆盖式更新）；key 为 NULL 的行不参与唯一约束
    __table_args__ = (
        Index(
            "ix_memory_items_user_key",
            "user_id",
            "mem_key",
            unique=True,
            sqlite_where=text("mem_key IS NOT NULL"),
            postgresql_where=text("mem_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # 类别：preference（偏好/口径）| fact（事实/背景）
    type: Mapped[str] = mapped_column(String(16), default="fact")
    # 结构化主键（如 "报销上限"）：同主题新值覆盖旧值；无明确主题时为 NULL
    mem_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 记忆内容（一句话，注入 prompt / 参与召回）
    content: Mapped[str] = mapped_column(Text)
    # 来源会话与消息（追溯）
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType(), nullable=True, index=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType(), nullable=True)
    # 向量（pgvector 模式为 Vector(N)，sqlite 模式为 JSON）；与 chunks.embedding 同维
    embedding: Mapped[list[float]] = mapped_column(get_vector_type(get_settings().embedding_dim))
    # LRU 淘汰依据：最近一次被召回命中（而非创建时间——老而常用的记忆不该被淘汰）
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
