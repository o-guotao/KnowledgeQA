"""诊断脚本：复现"langchain 短期记忆"召回混入 langgraph 内容的问题。
分别打印 向量召回 / BM25 召回 / RRF 融合 的 top 结果与文档名，定位混入环节。"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, ".")

from app.db import SessionLocal
from app.services.embedding import embed_query
from app.services.rag import _vector_recall, _keyword_recall, _rrf_fuse


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else Path("diag_query.txt").read_text(encoding="utf-8").strip()
    user_id = uuid.UUID(sys.argv[2]) if len(sys.argv) > 2 else None

    async with SessionLocal() as db:
        if user_id is None:
            from sqlalchemy import select
            from app.models.chunk import Chunk
            row = (await db.execute(select(Chunk.user_id).limit(1))).scalar_one_or_none()
            if row is None:
                print("库里没有任何 chunk，先上传文档再诊断")
                return
            user_id = row
        print(f"query = {query!r}  user = {user_id}\n")

        qvec = await embed_query(query)
        k = 10
        vec = await _vector_recall(db, user_id, qvec, k)
        kw = await _keyword_recall(db, user_id, query, k)
        fused = _rrf_fuse(vec, kw or [], k)

        def show(title, items):
            print(f"---- {title} ----")
            if not items:
                print("  (空)")
                return
            for i, c in enumerate(items, 1):
                head = c.content[:60].replace("\n", " ")
                print(f"  {i}. [{c.score}] {c.document_name} | {head}")
            print()

        show("向量召回", vec)
        show("BM25 召回", kw or [])
        show("RRF 融合（最终进 prompt 前的重排输入）", fused)


asyncio.run(main())
