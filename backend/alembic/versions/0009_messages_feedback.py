"""messages 增加答案反馈字段（点赞/点踩）

Revision ID: 0009_messages_feedback
Revises: 0008_chunks_parent_block
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_messages_feedback"
down_revision = "0008_chunks_parent_block"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # feedback: up | down | NULL（未反馈）
    op.add_column("messages", sa.Column("feedback", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "feedback")
