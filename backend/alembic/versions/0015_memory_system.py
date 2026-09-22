"""记忆系统：sessions 摘要列 + memory_items 长期记忆表

Revision ID: 0015_memory_system
Revises: 0014_eval_center
Create Date: 2026-09-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_memory_system"
down_revision = "0014_eval_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # L2：会话 rolling summary 与摘要水位
    op.add_column("sessions", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("summarized_until", sa.DateTime(timezone=True), nullable=True))
    # L3：长期记忆条目（向量列与 chunks 相同的方言处理，见 storage_compat；
    # 迁移内无法直接引用 settings，用与 chunks 建表一致的 vector 类型生成）
    from app.storage_compat import get_vector_type
    from app.config import get_settings

    op.create_table(
        "memory_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(16), server_default="fact", nullable=False),
        sa.Column("mem_key", sa.String(128), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("embedding", get_vector_type(get_settings().embedding_dim)),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_memory_items_user_id", "memory_items", ["user_id"])
    op.create_index("ix_memory_items_session_id", "memory_items", ["session_id"])
    op.create_index(
        "ix_memory_items_user_key",
        "memory_items",
        ["user_id", "mem_key"],
        unique=True,
        sqlite_where=sa.text("mem_key IS NOT NULL"),
        postgresql_where=sa.text("mem_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_memory_items_user_key", table_name="memory_items")
    op.drop_index("ix_memory_items_session_id", table_name="memory_items")
    op.drop_index("ix_memory_items_user_id", table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_column("sessions", "summarized_until")
    op.drop_column("sessions", "summary")
