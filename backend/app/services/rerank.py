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


def _elbow_cutoff(scores: list[float], min_k: int, max_k: int) -> int:
    """分数断崖截断：top_k 作上限，证据集中（分数出现显著落差）时少取。

    在 [min_k, max_k) 的切点窗口内找最大相邻降点；显著性 = 降点幅度 ≥ max(1.0, 2×中位数)
    （bge-reranker 输出 logits，1.0 是绝对幅度下限，防小波动误截）。
    不显著则取满 max_k。
    """
    n = min(len(scores), max_k)
    if n <= min_k:
        return n
    drops = [scores[i] - scores[i + 1] for i in range(n - 1)]
    # 切点 i 表示保留前 i+1 个；窗口保证至少留 min_k 个
    candidates = [(drops[i], i + 1) for i in range(min_k - 1, n - 1)]
    if not candidates:
        return n
    max_drop, cut = max(candidates)
    median = sorted(drops)[len(drops) // 2]
    if max_drop >= max(1.0, 2.0 * median):
        return cut
    return n


async def rerank(query: str, candidates: list, top_k: int, adaptive: bool = False, min_k: int = 3) -> list:
    """对候选块按与 query 的相关性重排，返回 top_k。

    candidates 为任意带 .content 属性的对象（如 RetrievedChunk）。
    重排失败时降级为原顺序截断（记日志），保证召回链路可用。
    adaptive=True（auto 模式）时按分数断崖截断：top_k 退化为上限，下限 min_k。
    """
    if not candidates:
        return []
    if len(candidates) <= top_k:
        return candidates

    def _score_sync() -> list[float]:
        model = _load_reranker()
        # fastembed 0.8 签名：rerank(query, documents) -> scores
        documents = [c.content for c in candidates]
        return [float(s) for s in model.rerank(query, documents)]

    try:
        scores = await asyncio.to_thread(_score_sync)
    except Exception as exc:
        logger.warning(
            "rerank failed, fallback to coarse order: %s",
            exc, extra={"event": "rerank_degraded"},
        )
        return candidates[:top_k]

    scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    k = top_k
    if adaptive:
        k = _elbow_cutoff([s for _, s in scored], min_k, top_k)
    result = [c for c, _ in scored[:k]]
    logger.info(
        "rerank done: %d candidates -> top %d%s (top score %.4f)",
        len(candidates), k, "/adaptive" if adaptive and k != top_k else "",
        scored[0][1] if scored else 0.0,
        extra={"event": "rerank"},
    )
    return result
