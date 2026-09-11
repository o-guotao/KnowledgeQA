"""documents 团队空间：visibility 列（private|team，历史行全部私有）

Revision ID: 0013_document_visibility
Revises: 0012_document_version_ingest
Create Date: 2026-09-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_document_visibility"
down_revision = "0012_document_version_ingest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("visibility", sa.String(16), server_default="private", nullable=False),
    )
    op.create_index("ix_documents_visibility", "documents", ["visibility"])


def downgrade() -> None:
    op.drop_index("ix_documents_visibility", table_name="documents")
    op.drop_column("documents", "visibility")
