"""documents 增加文件夹与标签（文档组织）

Revision ID: 0010_documents_folder_tags
Revises: 0009_messages_feedback
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_documents_folder_tags"
down_revision = "0009_messages_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("folder", sa.String(128), server_default="", nullable=False))
    op.add_column("documents", sa.Column("tags", sa.JSON(), nullable=True))
    op.create_index("ix_documents_folder", "documents", ["folder"])
    # 既有行 tags 默认空数组
    op.execute("UPDATE documents SET tags = '[]' WHERE tags IS NULL")


def downgrade() -> None:
    op.drop_index("ix_documents_folder", table_name="documents")
    op.drop_column("documents", "tags")
    op.drop_column("documents", "folder")
