"""评测中心：eval_datasets / eval_runs / eval_run_items + usage_records 分阶段耗时列

Revision ID: 0014_eval_center
Revises: 0013_document_visibility
Create Date: 2026-09-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_eval_center"
down_revision = "0013_document_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("source", sa.String(16), server_default="upload", nullable=False),
        sa.Column("item_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payload", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Uuid(), sa.ForeignKey("eval_datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(128), server_default="", nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_eval_runs_status_created", "eval_runs", ["status", "created_at"])
    op.create_index("ix_eval_runs_created", "eval_runs", ["created_at"])
    op.create_table(
        "eval_run_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("gold_doc", sa.String(256), nullable=False),
        sa.Column("ranks", sa.JSON(), nullable=False),
    )
    op.create_index("ix_eval_run_items_run_id", "eval_run_items", ["run_id"])

    # 线上分阶段耗时（chat 链路打点）
    op.add_column("usage_records", sa.Column("ttft_ms", sa.Float(), nullable=True))
    op.add_column("usage_records", sa.Column("total_ms", sa.Float(), nullable=True))
    op.add_column("usage_records", sa.Column("recall_ms", sa.Float(), nullable=True))
    op.add_column("usage_records", sa.Column("rerank_ms", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_records", "rerank_ms")
    op.drop_column("usage_records", "recall_ms")
    op.drop_column("usage_records", "total_ms")
    op.drop_column("usage_records", "ttft_ms")
    op.drop_index("ix_eval_run_items_run_id", table_name="eval_run_items")
    op.drop_table("eval_run_items")
    op.drop_index("ix_eval_runs_created", table_name="eval_runs")
    op.drop_index("ix_eval_runs_status_created", table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_table("eval_datasets")
