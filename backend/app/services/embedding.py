"""本地 BGE embedding（fastembed/ONNX）。模型首次运行下载，compose 中挂载缓存卷。

fastembed 为重量级依赖，采用函数内懒加载，保证仅导入契约层时无需安装。
启动时调用 verify_dimension() 校验模型实际维度与配置一致，避免写入 vector 列时才报错。
"""
import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_model = None
_verified_dim: int | None = None


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


async def verify_dimension() -> int:
    """启动时校验：模型实际输出维度必须等于 config.embedding_dim，
    否则向量写入 vector(N) 列会报晦涩的类型错误。返回实际维度。"""
    global _verified_dim
    if _verified_dim is not None:
        return _verified_dim
    settings = get_settings()
    sample = await embed_texts(["维度校验"])
    actual = len(sample[0])
    if actual != settings.embedding_dim:
        raise RuntimeError(
            f"embedding 维度不匹配：模型 {settings.embedding_model} 实际输出 {actual} 维，"
            f"但 EMBEDDING_DIM={settings.embedding_dim}，迁移列为 vector(512)。"
            f"请统一 EMBEDDING_DIM 与模型，并重建 chunks 表与索引。"
        )
    _verified_dim = actual
    logger.info("embedding dimension verified: %d", actual)
    return actual
