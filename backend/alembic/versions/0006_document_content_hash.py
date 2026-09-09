"""documents.content_hash + 部分唯一索引（用户级内容判重）

Revision ID: 0006_document_content_hash
Revises: 0005_model_inference_params
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_document_content_hash"
down_revision = "0005_model_inference_params"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SHA-256 十六进制为 64 字符；存量行 content_hash 为 NULL（不参与哈希判重，仅按文件名粗查）
    op.add_column("documents", sa.Column("content_hash", sa.String(64), nullable=True))
    # 并发双传兜底：同一用户同一内容只允许一条；NULL 行不参与唯一性
    op.create_index(
        "ix_documents_user_content_hash",
        "documents",
        ["user_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("content_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_documents_user_content_hash", table_name="documents")
    op.drop_column("documents", "content_hash")
