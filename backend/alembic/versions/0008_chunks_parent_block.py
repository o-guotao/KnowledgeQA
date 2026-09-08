"""chunks 增加父子块字段（语义分块：小块召回 + 大块上下文）

Revision ID: 0008_chunks_parent_block
Revises: 0007_chunks_content_tsv
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_chunks_parent_block"
down_revision = "0007_chunks_content_tsv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("parent_id", sa.Uuid(), nullable=True))
    op.add_column("chunks", sa.Column("block_type", sa.String(16), server_default="child", nullable=False))
    op.create_foreign_key(
        "fk_chunks_parent_id", "chunks", "chunks", ["parent_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_chunks_parent_id", "chunks", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_parent_id", table_name="chunks")
    op.drop_constraint("fk_chunks_parent_id", "chunks", type_="foreignkey")
    op.drop_column("chunks", "block_type")
    op.drop_column("chunks", "parent_id")
