"""widen model_configs.api_key_hint

Revision ID: 0004_widen_api_key_hint
Revises: 0003_model_configs
Create Date: 2026-09-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_widen_api_key_hint"
down_revision = "0003_model_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # api_key_hint 掩码长度与 api_key 等长（最长 512），原 varchar(16) 无法容纳真实 provider key
    op.alter_column("model_configs", "api_key_hint", type_=sa.String(512), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("model_configs", "api_key_hint", type_=sa.String(16), existing_nullable=False)
