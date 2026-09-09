"""chunks 增加全文检索列 content_tsv（混合检索关键词召回用）

Revision ID: 0007_chunks_content_tsv
Revises: 0006_document_content_hash
Create Date: 2026-09-08

仅 postgresql 生效（tsvector/GIN 为 PG 特性）；sqlite 由应用层 LIKE 退化实现，无需此列。
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_chunks_content_tsv"
down_revision = "0006_document_content_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'simple' 分词对中英文都按空白/标点切，比默认 english 更适合中文场景
    op.execute(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chunks_content_tsv ON chunks USING gin(content_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv")
