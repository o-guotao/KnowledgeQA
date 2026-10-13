"""评估运行器：建库 → 检索 →（可选）生成+评审 → 指标 → 落盘（断点续跑）。

- 知识库按切分三要素（strategy/size/overlap）缓存于 results/_kb/，语料指纹不变则复用
- 每轮实验结果落盘 results/<tag>/（config.json + items.jsonl + summary.json）
- 断点续跑：已完成的题目跳过；--force 归档旧结果后重跑
- 生成与评审需 DEEPSEEK_API_KEY（根 .env）；无 key 时自动降级为仅检索层指标
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import ExperimentConfig, apply_config
from . import metrics as M

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/eval/
DEFAULT_CORPUS_DIR = BASE_DIR / "dataset" / "corpus"
RESULTS_DIR = BASE_DIR / "results"
KB_DIR = RESULTS_DIR / "_kb"

DEMO_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ROUTER_SESSION_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

# prompt 变体（生成参数变量）。default=None 表示用线上 rag.RAG_SYSTEM_PROMPT
PROMPT_VARIANTS: dict[str, str | None] = {
    "default": None,
    "concise": (
        "你是企业内部知识问答助手。仅依据用户消息中 <<<RETRIEVED_DATA ... RETRIEVED_DATA>>> "
        "包裹的资料回答；资料不足时直接说明不知道，不要编造。"
        "回答控制在 120 字以内，用 [1] [2] 角标标注引用来源。"
    ),
}


def load_questions(path: Path) -> list[dict]:
    """加载评估集并归一化字段（兼容旧集 gold_doc 单数字段，旧集无参考答案则生成层指标跳过）。"""
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        gold_docs = obj.get("gold_docs") or ([obj["gold_doc"]] if obj.get("gold_doc") else [])
        items.append({
            "id": obj.get("id") or f"q{len(items) + 1:02d}",
            "q": obj["q"],
            "gold_docs": gold_docs,
            "gold_keywords": obj.get("gold_keywords") or [],
            "reference_answer": obj.get("reference_answer") or "",
            "type": obj.get("type") or "factual",
            "difficulty": obj.get("difficulty") or "easy",
        })
    return items


def make_provider(model: str | None = None):
    """由 Settings 构造 DeepSeek ProviderConfig；无 API key 返回 None。"""
    from app.config import get_settings
    from app.services.model_configs import ProviderConfig

    s = get_settings()
    if not s.deepseek_api_key:
        return None
    return ProviderConfig(
        base_url=s.deepseek_base_url,
        model_name=model or s.deepseek_model,
        api_key=s.deepseek_api_key,
        timeout_seconds=s.deepseek_timeout_seconds,
        price_input_per_million=s.deepseek_price_input_per_million,
        price_output_per_million=s.deepseek_price_output_per_million,
    )


def _corpus_fingerprint(cfg: ExperimentConfig, corpus_dir: Path) -> dict:
    fp: dict = {"strategy": cfg.chunk_strategy, "chunk_size": cfg.chunk_size,
                "chunk_overlap": cfg.chunk_overlap, "files": {}}
    for p in sorted(corpus_dir.iterdir()):
        if p.suffix.lower() in (".md", ".txt"):
            st = p.stat()
            fp["files"][p.name] = [st.st_size, st.st_mtime_ns]
    return fp


async def _ingest(factory, cfg: ExperimentConfig, corpus_dir: Path) -> int:
    """切分语料 + embedding 入库（复刻 worker 的 window/semantic 两路逻辑）。"""
    from app.config import get_settings
    from app.models.chunk import Chunk
    from app.models.document import Document
    from app.services.chunking import split_semantic, split_text
    from app.services.embedding import embed_texts

    settings = get_settings()
    doc_ids: dict[str, uuid.UUID] = {}
    texts: list[str] = []
    pending: list[dict] = []  # 按 texts 顺序的块元数据
    for path in sorted(corpus_dir.iterdir()):
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        text = path.read_text(encoding="utf-8")
        doc_id = uuid.uuid4()
        doc_ids[path.name] = doc_id
        if cfg.chunk_strategy == "semantic":
            blocks = split_semantic(text, settings.chunk_size, settings.chunk_overlap)
            for bi, b in enumerate(blocks):
                pending.append({"doc_id": doc_id, "kind": "parent", "group": bi,
                                "content": b.parent_content})
                texts.append(b.parent_content)
                for child in b.children:
                    pending.append({"doc_id": doc_id, "kind": "child", "group": bi,
                                    "content": child.content,
                                    "start_offset": child.start_offset,
                                    "end_offset": child.end_offset})
                    texts.append(child.content)
        else:
            pieces = split_text(text, settings.chunk_size, settings.chunk_overlap)
            for piece in pieces:
                pending.append({"doc_id": doc_id, "kind": "child", "group": 0,
                                "content": piece.content, "chunk_index": piece.chunk_index,
                                "start_offset": piece.start_offset, "end_offset": piece.end_offset})
                texts.append(piece.content)
        print(f"  [ingest] {path.name}: {len(blocks) if cfg.chunk_strategy == 'semantic' else len(pieces)} "
              f"{'blocks' if cfg.chunk_strategy == 'semantic' else 'chunks'}")

    print(f"  [embed] {len(texts)} chunks ...")
    vectors = await embed_texts(texts)

    async with factory() as db:
        for name, did in doc_ids.items():
            db.add(Document(
                id=did, user_id=DEMO_USER_ID, filename=name, object_key=f"eval/{name}",
                status="ready", chunk_count=0,
            ))
        parent_ids: dict[tuple, uuid.UUID] = {}
        chunk_count = 0
        for meta, vec in zip(pending, vectors, strict=True):
            if meta["kind"] == "parent":
                parent = Chunk(
                    document_id=meta["doc_id"], user_id=DEMO_USER_ID, chunk_index=chunk_count,
                    content=meta["content"], block_type="parent", embedding=vec,
                )
                db.add(parent)
                await db.flush()
                parent_ids[(meta["doc_id"], meta["group"])] = parent.id
            else:
                db.add(Chunk(
                    document_id=meta["doc_id"], user_id=DEMO_USER_ID,
                    chunk_index=meta.get("chunk_index", chunk_count),
                    content=meta["content"],
                    start_offset=meta.get("start_offset", 0), end_offset=meta.get("end_offset", 0),
                    block_type="child",
                    parent_id=parent_ids.get((meta["doc_id"], meta["group"])),
                    embedding=vec,
                ))
            chunk_count += 1
        await db.commit()
    return chunk_count


async def ensure_kb(cfg: ExperimentConfig, corpus_dir: Path):
    """按语料目录+切分三要素缓存知识库；语料指纹变化时重建。返回 (session factory, 块数或 None 表示复用)。"""
    from app.db import Base

    strategy, size, overlap = cfg.kb_key()
    KB_DIR.mkdir(parents=True, exist_ok=True)
    db_path = KB_DIR / f"kb_{corpus_dir.name}_{strategy}_{size}_{overlap}.db"
    fp_path = db_path.with_suffix(".json")
    fp = _corpus_fingerprint(cfg, corpus_dir)
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    if db_path.exists() and fp_path.exists() and json.loads(fp_path.read_text(encoding="utf-8")) == fp:
        engine = create_async_engine(url, connect_args={"check_same_thread": False})
        return async_sessionmaker(engine, expire_on_commit=False), None

    if db_path.exists():
        db_path.unlink()
    engine = create_async_engine(url, connect_args={"check_same_thread": False})
    import app.models  # noqa: F401 确保全部模型已注册

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    total = await _ingest(factory, cfg, corpus_dir)
    fp_path.write_text(json.dumps(fp), encoding="utf-8")
    return factory, total


async def _decide_top_k(cfg: ExperimentConfig, router_provider, q: str) -> tuple[int, str]:
    """top_k 决策：fixed / auto（L2 启发式）/ router（L4 LLM 分类，失败回退 L2）。"""
    from app.services import rag

    if cfg.top_k_mode == "auto":
        return rag.auto_top_k(q), "auto"
    if cfg.top_k_mode == "router":
        if router_provider is None:
            return rag.auto_top_k(q), "router:no-key-fallback"
        from app.services.agents.router import RouterFallback, route

        try:
            decision, _, _ = await route(router_provider, ROUTER_SESSION_ID, q)
            return decision.top_k, f"router:{decision.category}"
        except RouterFallback:
            return rag.auto_top_k(q), "router:fallback"
    return cfg.top_k, "fixed"


async def _generate(provider, q: str, chunks: list, cfg: ExperimentConfig) -> str:
    from app.services import rag
    from app.services.llm_client import chat

    system = PROMPT_VARIANTS[cfg.prompt_variant] or rag.RAG_SYSTEM_PROMPT
    user = rag.build_rag_user_content(q, chunks[: cfg.context_chunks])
    result = await chat(
        provider,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=800, temperature=0, timeout_cap=60.0,
    )
    return result.content


def _run_dir(tag: str) -> Path:
    return RESULTS_DIR / tag


def _load_done(run_dir: Path) -> dict[str, dict]:
    items_file = run_dir / "items.jsonl"
    done: dict[str, dict] = {}
    if items_file.exists():
        for line in items_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                done[obj["id"]] = obj
    return done


async def run_experiment(
    cfg: ExperimentConfig,
    questions: list[dict],
    *,
    with_llm: bool = False,
    force: bool = False,
    sample: int | None = None,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
) -> dict:
    """跑一轮实验，返回 summary。断点续跑：已落盘题目直接复用。"""
    from app.config import get_settings  # noqa: F401 确保 app 可导入
    from app.services import rag
    from app.services.embedding import embed_query

    run_tag = cfg.tag if corpus_dir == DEFAULT_CORPUS_DIR else f"{cfg.tag}__{corpus_dir.name}"
    run_dir = _run_dir(run_tag)
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot = cfg.to_snapshot()

    config_file = run_dir / "config.json"
    if config_file.exists() and not force:
        old = json.loads(config_file.read_text(encoding="utf-8"))
        if old != snapshot:
            raise SystemExit(
                f"[{cfg.tag}] 已存在不同配置的结果，请先 --force 归档重跑或更换 tag"
            )
    if force and (run_dir / "items.jsonl").exists():
        archive = run_dir / f"items.archived-{int(time.time())}.jsonl"
        (run_dir / "items.jsonl").rename(archive)
    config_file.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    done = _load_done(run_dir) if not force else {}

    def _incomplete(qid: str) -> bool:
        """with_llm 模式下，缺评审/生成失败的题视为未完成（支持先跑检索层、后补生成层）。"""
        if qid not in done:
            return True
        if not with_llm:
            return False
        it = done[qid]
        return it.get("judge") is None and not it.get("judge_skipped")

    todo = [q for q in questions if _incomplete(q["id"])]
    if sample:
        todo = todo[:sample]

    print(f"\n=== 实验 {run_tag}：{cfg.desc} ===")
    t0 = time.perf_counter()
    with apply_config(cfg):
        factory, built = await ensure_kb(cfg, corpus_dir)
        if built is not None:
            print(f"[kb] 新建知识库 {cfg.kb_key()}：{built} chunks")

        router_provider = make_provider() if cfg.top_k_mode == "router" else None
        gen_provider = make_provider(cfg.gen_model) if with_llm else None
        if with_llm and gen_provider is None:
            print("[warn] 未配置 DEEPSEEK_API_KEY，本轮降级为仅检索层指标")
        if cfg.top_k_mode == "router" and router_provider is None:
            print("[warn] 未配置 DEEPSEEK_API_KEY，L4 Router 全部回退 L2 启发式")

        items_file = run_dir / "items.jsonl"
        with items_file.open("a", encoding="utf-8") as fout:
            for i, q in enumerate(todo, 1):
                k, k_src = await _decide_top_k(cfg, router_provider, q["q"])
                vec = await embed_query(q["q"])
                timing: dict = {}
                async with factory() as db:
                    chunks = await rag.retrieve(
                        db, DEMO_USER_ID, vec, top_k=k, query_text=q["q"], timing=timing
                    )
                m = M.retrieval_metrics(
                    [(c.document_name, c.snippet or c.content) for c in chunks],
                    q["gold_docs"], q["gold_keywords"],
                )
                item = {
                    "id": q["id"], "q": q["q"], "type": q["type"], "difficulty": q["difficulty"],
                    "top_k": k, "top_k_src": k_src,
                    **{kk: m[kk] for kk in ("k", "gold_hits", "hit", "first_rank", "precision", "rr")},
                    "retrieved": [
                        {"rank": r, "doc": c.document_name, "gold": g,
                         "preview": (c.snippet or c.content)[:60]}
                        for r, (c, g) in enumerate(zip(chunks, m["flags"], strict=True), 1)
                    ],
                    "recall_ms": timing.get("recall_ms"),
                    "rerank_ms": timing.get("rerank_ms"),
                }

                if with_llm and gen_provider is not None:
                    contexts = [c.content for c in chunks[: cfg.context_chunks]]
                    try:
                        answer = await _generate(gen_provider, q["q"], chunks, cfg)
                        item["answer"] = answer
                        if q["reference_answer"]:
                            from . import judge

                            item["judge"] = await judge.judge_all(
                                gen_provider, q["q"], answer, q["reference_answer"], contexts
                            )
                        else:
                            item["judge"] = None
                            item["judge_skipped"] = "no reference_answer"
                    except Exception as exc:  # 单题失败不中断整轮
                        logger.warning("生成/评审失败 %s：%s", q["id"], exc)
                        item["error"] = str(exc)[:200]

                fout.write(json.dumps(item, ensure_ascii=False) + "\n")
                fout.flush()
                done[q["id"]] = item
                mark = "✓" if item["hit"] else "✗"
                judged = "J" if item.get("judge") else " "
                print(f"  [{run_tag} {i:03d}/{len(todo)}] {mark}{judged} k={k}({k_src}) "
                      f"rank={item['first_rank']} prec={item['precision']:.2f} {q['q'][:28]}")

    # 聚合全部题目（含续跑复用部分）
    items = [done[q["id"]] for q in questions if q["id"] in done]
    summary = {
        "tag": run_tag,
        "desc": cfg.desc,
        "total": len(items),
        "with_llm": with_llm,
        "retrieval": M.aggregate_retrieval(items),
        "avg_top_k": round(sum(it["top_k"] for it in items) / len(items), 2) if items else 0,
        "avg_recall_ms": round(
            sum(it["recall_ms"] for it in items if it.get("recall_ms"))
            / max(1, sum(1 for it in items if it.get("recall_ms"))), 1),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if with_llm:
        from . import judge

        summary["generation"] = judge.aggregate_generation(items)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    r = summary["retrieval"]
    print(f"[{run_tag}] recall={r['recall_at_k']:.2%} precision={r['precision_at_k']:.2%} "
          f"mrr={r['mrr']:.3f}（{summary['total']} 题，{summary['elapsed_s']}s）")
    return summary
