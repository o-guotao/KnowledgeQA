"""本地 BGE embedding（fastembed/ONNX）。模型首次运行下载，compose 中挂载缓存卷。

fastembed 为重量级依赖，采用函数内懒加载，保证仅导入契约层时无需安装。
"""
import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_model = None


def _load_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding  # 懒加载

        settings = get_settings()
        logger.info("loading embedding model %s", settings.embedding_model)
        _model = TextEmbedding(model_name=settings.embedding_model)
    return _model


def _embed_sync(texts: list[str]) -> list[list[float]]:
    model = _load_model()
    return [vec.tolist() for vec in model.embed(texts)]


async def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """批量向量化，在线程池中执行避免阻塞事件循环。"""
    if not texts:
        return []
    results: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        results.extend(await asyncio.to_thread(_embed_sync, batch))
    return results


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text]))[0]
