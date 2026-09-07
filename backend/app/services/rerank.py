"""cross-encoder 重排序：召回粗排 top N 后精排取 top_k。

向量召回是粗排（快但排序粗糙），cross-encoder 逐对计算"问题-文档块"相关性分数，
把相关块从粗排的 8-15 位提到前 3，是召回精度提升投入产出比最高的一环。

默认关闭（RERANK_ENABLED=false）：reranker 依赖 fastembed（onnxruntime），
非 Docker(Python 3.12) 环境不可用。生产 Docker 开启。
"""
import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_reranker = None


def _load_reranker():
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # 懒加载

        settings = get_settings()
        logger.info("loading reranker model %s", settings.rerank_model)
        _reranker = TextCrossEncoder(model_name=settings.rerank_model)
    return _reranker


def rerank_available() -> bool:
    """重排是否启用且可用（不触发模型加载，仅看配置）。"""
    return get_settings().rerank_enabled


async def rerank(query: str, candidates: list, top_k: int) -> list:
    """对候选块按与 query 的相关性重排，返回 top_k。

    candidates 为任意带 .content 属性的对象（如 RetrievedChunk）。
    重排失败时降级为原顺序截断（记日志），保证召回链路可用。
    """
    if not candidates:
        return []
    if len(candidates) <= top_k:
        return candidates

    def _score_sync() -> list[float]:
        model = _load_reranker()
        pairs = [(query, c.content) for c in candidates]
        return [float(s) for s in model.rerank(pairs)]

    try:
        scores = await asyncio.to_thread(_score_sync)
    except Exception as exc:
        logger.warning(
            "rerank failed, fallback to coarse order: %s",
            exc, extra={"event": "rerank_degraded"},
        )
        return candidates[:top_k]

    scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    result = [c for c, _ in scored[:top_k]]
    logger.info(
        "rerank done: %d candidates -> top %d (top score %.4f)",
        len(candidates), top_k, scored[0][1] if scored else 0.0,
        extra={"event": "rerank"},
    )
    return result
