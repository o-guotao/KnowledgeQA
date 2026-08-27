"""add storage_orphans table

Revision ID: 0002_orphans
Revises: 0001_init
Create Date: 2026-08-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_orphans"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_orphans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("reason", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_storage_orphans_object_key", "storage_orphans", ["object_key"])


def downgrade() -> None:
    op.drop_table("storage_orphans")
