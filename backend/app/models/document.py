import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.storage_compat import UUIDType

# uploaded -> processing -> ready / failed
# no_text：上传时即判定为纯图片 PDF（无文字层），保留原文件但不投递切分任务，供预览/将来 OCR
DOCUMENT_STATUSES = ("uploaded", "processing", "ready", "failed", "no_text")


class Document(Base):
    __tablename__ = "documents"
    # 用户级内容判重的部分唯一索引（NULL 行不参与）。sqlite/pg 双方言 where 兼容。
    __table_args__ = (
        Index(
            "ix_documents_user_content_hash",
            "user_id",
            "content_hash",
            unique=True,
            postgresql_where=text("content_hash IS NOT NULL"),
            sqlite_where=text("content_hash IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDType(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(256))
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 文档组织：文件夹（单层路径如 "制度/人事"）与标签（JSON 字符串数组）
    folder: Mapped[str] = mapped_column(String(128), default="", index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # 可见性：private（仅本人/admin）| team（团队空间，全部登录用户可检索/预览）
    visibility: Mapped[str] = mapped_column(String(16), default="private", index=True)
    object_key: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="uploaded", index=True)
    chunk_size: Mapped[int] = mapped_column(Integer, default=512)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=64)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 增量更新与失效检测：version 仅内容变更 +1；ingest_signature 为最近成功入库时的
    # 切分策略/参数 + embedding 配置快照（见 services/doc_sync.py），空串表示历史未记录
    version: Mapped[int] = mapped_column(Integer, default=1)
    ingest_signature: Mapped[str] = mapped_column(String(128), default="")
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
