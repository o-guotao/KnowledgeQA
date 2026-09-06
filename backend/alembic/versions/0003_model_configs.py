"""add user model configurations

Revision ID: 0003_model_configs
Revises: 0002_orphans
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_model_configs"
down_revision = "0002_orphans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_hint", sa.String(16), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), server_default="60", nullable=False),
        sa.Column("price_input_per_million", sa.Float(), nullable=True),
        sa.Column("price_output_per_million", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_model_configs_user_id", "model_configs", ["user_id"])
    op.create_index(
        "uq_model_configs_active_per_user",
        "model_configs",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_model_configs_active_per_user", table_name="model_configs")
    op.drop_index("ix_model_configs_user_id", table_name="model_configs")
    op.drop_table("model_configs")
