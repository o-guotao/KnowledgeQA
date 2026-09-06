"""add configurable inference params to model_configs

Revision ID: 0005_model_inference_params
Revises: 0004_widen_api_key_hint
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_model_inference_params"
down_revision = "0004_widen_api_key_hint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_configs", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("model_configs", sa.Column("top_p", sa.Float(), nullable=True))
    op.add_column("model_configs", sa.Column("max_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("model_configs", "max_tokens")
    op.drop_column("model_configs", "top_p")
    op.drop_column("model_configs", "temperature")
