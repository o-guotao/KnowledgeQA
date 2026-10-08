import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.storage_compat import UUIDType

GRANTEE_TYPES = ("user", "group")
# write 蕴含 read；同一 (document, grantee) 仅存一条最高权限
GRANT_PERMISSIONS = ("read", "write")


class DocumentGrant(Base):
    __tablename__ = "document_grants"
    __table_args__ = (
        UniqueConstraint("document_id", "grantee_type", "grantee_id", name="uq_document_grants_target"),
        Index("ix_document_grants_grantee", "grantee_type", "grantee_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUIDType(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType(), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    grantee_type: Mapped[str] = mapped_column(String(8))  # user | group
    # 指向 users.id 或 groups.id，由 grantee_type 区分（不做复合 FK，应用层校验存在性）
    grantee_id: Mapped[uuid.UUID] = mapped_column(UUIDType())
    permission: Mapped[str] = mapped_column(String(8), default="read")  # read | write
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
