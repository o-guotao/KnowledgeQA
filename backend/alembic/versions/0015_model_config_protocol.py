"""模型配置协议字段：model_configs.protocol（openai | anthropic）

Revision ID: 0015_model_config_protocol
Revises: 0014_eval_center
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_model_config_protocol"
down_revision = "0014_eval_center"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 既有配置全部为 OpenAI 兼容协议，server_default 保证存量数据无感
    op.add_column(
        "model_configs",
        sa.Column("protocol", sa.String(20), server_default="openai", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("model_configs", "protocol")
