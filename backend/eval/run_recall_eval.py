"""召回命中率评测：量化混合检索 + 重排对召回的提升。

独立运行：只测召回（不需 LLM 生成 / DeepSeek key / MinIO / 启动后端），
直接用真实 fastembed BGE embedding 建 SQLite 知识库，对 30 条问句跑三组配置：

  baseline       单向量召回（无混合、无重排）
  hybrid         混合检索（向量 + 关键词 RRF，无重排）
  hybrid_rerank  混合检索 + cross-encoder 重排

指标：
  recall_hit   gold_doc 是否出现在 top_k 召回的来源文档中（命中率）
  mrr          gold_doc 首次命中排名的倒数均值（越靠前越好）

用法（conda langgraph 环境，已装 fastembed）：
    C:/Users/gys3894/.conda/envs/langgraph/python.exe -m eval.run_recall_eval
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

# ---- 环境：SQLite + 真实 fastembed embedding（在 import app 前设置） ----
os.environ.update({
    "DB_BACKEND": "sqlite",
    "DATABASE_URL": "sqlite:///./eval_recall.db",
    "STORAGE_BACKEND": "local",
    "EMBEDDING_BACKEND": "fastembed",
    "EMBEDDING_MODEL": "BAAI/bge-small-zh-v1.5",
    "EMBEDDING_DIM": "512",
    "ENVIRONMENT": "development",
    "RAG_TOP_K": "5",
    "RERANK_CANDIDATE_MULTIPLIER": "4",
})
# chunk_size/overlap 允许命令行环境变量覆盖（不设默认，便于制造区分度）
os.environ.setdefault("CHUNK_SIZE", "128")
os.environ.setdefault("CHUNK_OVERLAP", "32")

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, create_all_tables  # noqa: E402
from app.models.chunk import Chunk  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.services import rag  # noqa: E402
from app.services.chunking import split_text  # noqa: E402
from app.services.embedding import embed_query, embed_texts  # noqa: E402
from sqlalchemy import delete  # noqa: E402

BASE_DIR = Path(__file__).parent
DOCS_DIR = BASE_DIR / "sample_docs"
# 可用 --questions 指定问句文件（默认 questions.jsonl，难句集用 questions_hard.jsonl）
import argparse as _argparse  # noqa: E402

_parser = _argparse.ArgumentParser()
_parser.add_argument("--questions", default="questions.jsonl")
_args, _ = _parser.parse_known_args()
QUESTIONS_FILE = BASE_DIR / _args.questions
DB_FILE = "eval_recall.db"
DEMO_USER_ID = uuid.uuid4()


async def setup_knowledge_base() -> int:
    """切分样例文档 + 真实 embedding 入库。返回总块数。"""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    await create_all_tables()

    settings = get_settings()
    all_chunks: list[dict] = []
    doc_ids: dict[str, uuid.UUID] = {}
    for path in sorted(DOCS_DIR.iterdir()):
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        text = path.read_text(encoding="utf-8")
        pieces = split_text(text, settings.chunk_size, settings.chunk_overlap)
        doc_id = uuid.uuid4()
        doc_ids[path.name] = doc_id
        for p in pieces:
            all_chunks.append({
                "document_id": doc_id, "filename": path.name,
                "chunk_index": p.chunk_index, "content": p.content,
            })
        print(f"[ingest] {path.name}: {len(pieces)} chunks")

    texts = [c["content"] for c in all_chunks]
    print(f"[embed] {len(texts)} chunks ...")
    vectors = await embed_texts(texts)

    async with SessionLocal() as db:
        for name, did in doc_ids.items():
            db.add(Document(
                id=did, user_id=DEMO_USER_ID, filename=name, object_key=f"eval/{name}",
                status="ready", chunk_count=0,
            ))
        for c, vec in zip(all_chunks, vectors, strict=True):
            db.add(Chunk(
                document_id=c["document_id"], user_id=DEMO_USER_ID,
                chunk_index=c["chunk_index"], content=c["content"],
                block_type="child", embedding=vec,
            ))
        await db.commit()
    return len(all_chunks)


def load_questions() -> list[dict]:
    return [
        json.loads(line)
        for line in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def run_group(tag: str, hybrid: bool, rerank: bool, questions: list[dict]) -> dict:
    """跑一组配置，返回 recall_hit 命中率与 MRR。"""
    os.environ["HYBRID_SEARCH_ENABLED"] = "true" if hybrid else "false"
    os.environ["RERANK_ENABLED"] = "true" if rerank else "false"
    get_settings.cache_clear()
    # rerank 单例重置（baseline/hybrid 不加载 reranker，hybrid_rerank 加载一次）
    import app.services.rerank as rk
    rk._reranker = None

    hits = 0
    rr_sum = 0.0
    details = []
    for i, item in enumerate(questions, 1):
        q = item["q"]
        gold = item["gold_doc"]
        vec = await embed_query(q)
        async with SessionLocal() as db:
            chunks = await rag.retrieve(db, DEMO_USER_ID, vec, query_text=q)
        # gold_doc 首次命中的排名（1-based），未命中为 0
        rank = 0
        for idx, c in enumerate(chunks, 1):
            if c.document_name == gold:
                rank = idx
                break
        hit = rank > 0
        hits += hit
        rr_sum += 1.0 / rank if rank else 0.0
        details.append({"i": i, "q": q, "gold_doc": gold, "rank": rank, "hit": hit,
                        "cited": [c.document_name for c in chunks]})
        mark = "✓" if hit else "✗"
        print(f"  [{tag} {i:02d}/{len(questions)}] {mark} rank={rank} {q[:30]}")

    n = len(questions)
    return {
        "tag": tag, "total": n, "hits": hits,
        "recall_hit_rate": round(hits / n, 4),
        "mrr": round(rr_sum / n, 4),
        "details": details,
    }


async def main() -> None:
    print("=== 建知识库（真实 BGE embedding） ===")
    total_chunks = await setup_knowledge_base()
    print(f"[kb] {total_chunks} chunks ready\n")

    questions = load_questions()
    print(f"[eval] {len(questions)} questions\n")

    groups = [
        ("baseline", False, False),
        ("hybrid", True, False),
        ("hybrid_rerank", True, True),
    ]
    results = []
    for tag, hybrid, rerank in groups:
        print(f"=== 组：{tag} (hybrid={hybrid}, rerank={rerank}) ===")
        results.append(await run_group(tag, hybrid, rerank, questions))
        print()

    # 汇总对比
    print("=" * 60)
    print(f"{'配置':<16}{'recall命中率':<14}{'MRR':<8}{'命中/总数'}")
    print("-" * 60)
    for r in results:
        print(f"{r['tag']:<16}{r['recall_hit_rate']:<14.2%}{r['mrr']:<8.3f}{r['hits']}/{r['total']}")
    print("=" * 60)

    base = results[0]
    for r in results[1:]:
        dr = r["recall_hit_rate"] - base["recall_hit_rate"]
        dm = r["mrr"] - base["mrr"]
        print(f"{r['tag']} vs baseline: recall {dr:+.2%}, mrr {dm:+.3f}")

    # 逐条标注各组未命中/排名下降的题（定位混合检索/重排的实际作用点）
    print("\n=== 各组排名有差异的题（rank 变化） ===")
    by_q = {r["tag"]: {d["q"]: d["rank"] for d in r["details"]} for r in results}
    diff_count = 0
    for q in [item["q"] for item in questions]:
        ranks = {tag: by_q[tag][q] for tag, _, _ in groups}
        if len(set(ranks.values())) > 1:
            diff_count += 1
            print(f"  {q[:34]:<36} baseline={ranks['baseline']} hybrid={ranks['hybrid']} rerank={ranks['hybrid_rerank']}")
    if diff_count == 0:
        print("  （无：三组排名完全一致——知识库区分度不足，建议减小 chunk_size 或增加干扰文档）")

    # 落盘明细
    out_dir = BASE_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    summary = {r["tag"]: {k: v for k, v in r.items() if k != "details"} for r in results}
    (out_dir / "recall_compare_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for r in results:
        (out_dir / f"recall_{r['tag']}.json").write_text(
            json.dumps(r["details"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"\n明细已写入 {out_dir}")

    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
