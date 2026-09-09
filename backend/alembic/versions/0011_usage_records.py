"""usage_records 调用明细表（管理后台用量 / 成本报表）

Revision ID: 0011_usage_records
Revises: 0010_documents_folder_tags
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_usage_records"
down_revision = "0010_documents_folder_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("cost_cny", sa.Float(), server_default="0"),
        sa.Column("trace_id", sa.String(32), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_usage_records_user_id", "usage_records", ["user_id"])
    op.create_index("ix_usage_records_user_created", "usage_records", ["user_id", "created_at"])
    op.create_index("ix_usage_records_created", "usage_records", ["created_at"])
    op.create_index("ix_usage_records_model", "usage_records", ["model"])


def downgrade() -> None:
    op.drop_index("ix_usage_records_model", table_name="usage_records")
    op.drop_index("ix_usage_records_created", table_name="usage_records")
    op.drop_index("ix_usage_records_user_created", table_name="usage_records")
    op.drop_index("ix_usage_records_user_id", table_name="usage_records")
    op.drop_table("usage_records")
