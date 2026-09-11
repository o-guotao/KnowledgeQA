"""documents 增量更新与失效检测：version / ingest_signature / ingested_at

Revision ID: 0012_document_version_ingest
Revises: 0011_usage_records
Create Date: 2026-09-10
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0012_document_version_ingest"
down_revision = "0011_usage_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "documents", sa.Column("ingest_signature", sa.String(128), server_default="", nullable=False)
    )
    op.add_column("documents", sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True))

    # 回填 ready 历史行签名：假设其按当前部署 env 入库，避免迁移后全部误报 stale。
    # env 默认值与 app.config.Settings 对齐；chunk_size/chunk_overlap 取行内快照列。
    # 拼接用 ||（postgres 与 sqlite 均支持）。
    strategy = os.getenv("CHUNK_STRATEGY", "window")
    backend = os.getenv("EMBEDDING_BACKEND", "fastembed")
    model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    op.execute(
        sa.text(
            "UPDATE documents SET ingest_signature = "
            f"'{strategy}|' || chunk_size || '|' || chunk_overlap || '|{backend}|{model}' "
            "WHERE status = 'ready' AND ingest_signature = ''"
        )
    )


def downgrade() -> None:
    op.drop_column("documents", "ingested_at")
    op.drop_column("documents", "ingest_signature")
    op.drop_column("documents", "version")
