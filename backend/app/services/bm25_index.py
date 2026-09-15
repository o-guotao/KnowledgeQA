"""BM25 关键词索引（内存单例），替代 Postgres ts_rank / SQLite LIKE 的关键词召回。

- 分词：jieba（中文按词切分，英文/数字/编号保留完整 token），jieba 词典加载放线程避免阻塞
- 排序：rank_bm25.BM25Okapi —— 真正的 BM25（TF 饱和 k1、文档长度归一 b、IDF）
- 语料：全库 child 块；IDF 用全库统计，用户隔离在取 top 结果时按 user_id 过滤，
  团队空间（documents.visibility='team'）的块对全部登录用户可见
- 失效：以 (count, max(created_at), team 块数) 为指纹，每次查询前比对；worker 入库新块、
  文档删除（CASCADE 清块）、共享/取消共享都会改变指纹，触发懒重建。chunk 无更新路径，故指纹充分。
- 并发：构建在 asyncio.Lock 内 + to_thread，完成后原子替换，查询路径不阻塞事件循环

依赖缺失（rank_bm25/jieba 未安装）时 search() 返回 None，调用方回退数据库方案。
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document

logger = logging.getLogger(__name__)

try:
    import jieba
    from rank_bm25 import BM25Okapi

    _AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失时整体降级
    _AVAILABLE = False
    logger.warning("rank_bm25/jieba 未安装，BM25 召回不可用，将回退数据库关键词检索")

_CJK_RE = re.compile(r"[一-鿿]")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]")


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 清洗：小写、去空白、去纯标点（保留含中文或字母数字的 token）。"""
    tokens: list[str] = []
    for tok in jieba.lcut(text.lower()):
        tok = tok.strip()
        if not tok:
            continue
        if _CJK_RE.search(tok) or _ALNUM_RE.search(tok):
            tokens.append(tok)
    return tokens


@dataclass
class _Index:
    bm25: "BM25Okapi"
    chunk_ids: list[uuid.UUID]
    user_ids: list[uuid.UUID]
    # 团队空间标记：team 文档的块对全部登录用户可见（与 owner 过滤并联）
    team_flags: list[bool]
    fingerprint: tuple[int, object, int]


_state: _Index | None = None
_lock = asyncio.Lock()


async def _fingerprint(db: AsyncSession) -> tuple[int, object, int]:
    """失效指纹：(child 块数, max(created_at), team 文档的 child 块数)。
    第三项覆盖 share/unshare：可见性变化不改变块数与时间，但改变 team 块数，触发懒重建。"""
    row = (
        await db.execute(
            select(func.count(Chunk.id), func.max(Chunk.created_at)).where(Chunk.block_type == "child")
        )
    ).one()
    team_count = (
        await db.execute(
            select(func.count(Chunk.id))
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.block_type == "child", Document.visibility == "team")
        )
    ).scalar_one()
    return (row[0], row[1], team_count)


def _build(
    rows: list[tuple[uuid.UUID, uuid.UUID, str, str]], fingerprint: tuple[int, object, int]
) -> _Index:
    corpus = [_tokenize(content) for _, _, content, _ in rows]
    return _Index(
        bm25=BM25Okapi(corpus),
        chunk_ids=[r[0] for r in rows],
        user_ids=[r[1] for r in rows],
        team_flags=[r[3] == "team" for r in rows],
        fingerprint=fingerprint,
    )


async def _ensure_index(db: AsyncSession) -> _Index | None:
    global _state
    if not _AVAILABLE:
        return None
    fp = await _fingerprint(db)
    if _state is not None and _state.fingerprint == fp:
        return _state
    async with _lock:
        # 锁内重查指纹：并发等待者拿到锁时索引可能已被前一个请求重建
        fp = await _fingerprint(db)
        if _state is not None and _state.fingerprint == fp:
            return _state
        rows = (
            await db.execute(
                select(Chunk.id, Chunk.user_id, Chunk.content, Document.visibility)
                .join(Document, Chunk.document_id == Document.id)
                .where(Chunk.block_type == "child")
            )
        ).all()
        state = await asyncio.to_thread(_build, [(r[0], r[1], r[2], r[3]) for r in rows], fp)
        _state = state
        logger.info(
            "bm25 index rebuilt: %d chunks",
            len(state.chunk_ids),
            extra={"event": "bm25_index_rebuilt"},
        )
        return state


async def search(
    db: AsyncSession, user_id: uuid.UUID, query_text: str, limit: int
) -> list[tuple[uuid.UUID, float]] | None:
    """BM25 召回：返回 [(chunk_id, score)] 按分数降序；不可用/无结果返回 None 或 []。

    返回 None 表示 BM25 不可用（依赖缺失），调用方应回退数据库关键词检索。
    """
    state = await _ensure_index(db)
    if state is None:
        return None
    query_tokens = await asyncio.to_thread(_tokenize, query_text)
    if not query_tokens or not state.chunk_ids:
        return []
    scores = await asyncio.to_thread(state.bm25.get_scores, query_tokens)
    # 全局候选放大 10 倍再按用户过滤，避免 top 全是他人文档导致召回缺失
    candidate_n = min(len(state.chunk_ids), limit * 10)
    top_idx = scores.argsort()[::-1][:candidate_n]
    hits: list[tuple[uuid.UUID, float]] = []
    for i in top_idx:
        score = float(scores[i])
        if score <= 0:
            break  # 降序排列，后续都是 0 分（未命中任何查询词）
        if state.user_ids[i] != user_id and not state.team_flags[i]:
            continue
        hits.append((state.chunk_ids[i], round(score, 4)))
        if len(hits) >= limit:
            break
    return hits
