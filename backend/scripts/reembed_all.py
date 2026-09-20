"""一次性修复脚本：用当前 embedding 后端重算全部 chunk 向量。

背景：venv 曾因 onnxruntime 不兼容降级 hash embedding，入库向量无语义。
恢复 fastembed 后旧向量与新空间不兼容，需全量重算（child+parent 都算，
量级为全库块数，一次性）。
"""
import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select, update

from app.db import SessionLocal
from app.models.chunk import Chunk
from app.services.embedding import embed_texts


async def main() -> None:
    async with SessionLocal() as db:
        rows = (await db.execute(select(Chunk.id, Chunk.content))).all()
        total = len(rows)
        print(f"chunks to re-embed: {total}")
        batch = 64
        done = 0
        for i in range(0, total, batch):
            part = rows[i : i + batch]
            vectors = await embed_texts([content for _, content in part])
            for (cid, _), vec in zip(part, vectors, strict=True):
                await db.execute(
                    update(Chunk).where(Chunk.id == cid).values(embedding=vec)
                )
            await db.commit()
            done += len(part)
            print(f"  {done}/{total}")
        print("done.")


asyncio.run(main())
