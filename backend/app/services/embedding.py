"""本地 BGE embedding（fastembed/ONNX）。模型首次运行下载，compose 中挂载缓存卷。

fastembed 为重量级依赖，采用函数内懒加载，保证仅导入契约层时无需安装。
启动时调用 verify_dimension() 校验模型实际维度与配置一致，避免写入 vector 列时才报错。

本地无 Docker 演示降级：若 onnxruntime 在当前 Python 版本下 DLL 加载失败
（如 Python 3.14 无预编译 wheel），自动切换到确定性哈希向量——
只为让上传/切分/召回/回答链路跑通演示，召回质量无意义，生产必须用真实 embedding。
"""
import asyncio
import hashlib
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_model = None
_verified_dim: int | None = None
_use_hash_fallback = False


def _load_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding  # 懒加载

        settings = get_settings()
        logger.info("loading embedding model %s", settings.embedding_model)
        _model = TextEmbedding(model_name=settings.embedding_model)
    return _model


def _hash_embed_sync(texts: list[str]) -> list[list[float]]:
    """降级方案：确定性哈希向量，仅用于本地演示链路跑通。

    召回质量无意义（哈希无语义），但上传/切分/入库/召回/回答全链路可演示。
    生产环境（Docker + Python 3.12）用真实 BGE，不走此分支。
    """
    import numpy as np

    settings = get_settings()
    dim = settings.embedding_dim
    vectors = []
    for text in texts:
        # 用多轮哈希填充 dim 维，保证同文本同向量、不同文本差异大
        vec = np.zeros(dim, dtype=np.float32)
        for i in range(0, dim, 8):
            h = hashlib.sha256(f"{i}:{text}".encode()).digest()
            for j, b in enumerate(h):
                if i + j < dim:
                    vec[i + j] = (b - 128) / 128.0
        # L2 归一化，与真实 embedding 的余弦相似度计算兼容
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        vectors.append(vec.tolist())
    return vectors


def _embed_sync(texts: list[str]) -> list[list[float]]:
    global _use_hash_fallback
    if _use_hash_fallback:
        return _hash_embed_sync(texts)
    try:
        model = _load_model()
        return [vec.tolist() for vec in model.embed(texts)]
    except ImportError as exc:
        if "onnxruntime" in str(exc) or "DLL" in str(exc):
            logger.warning(
                "onnxruntime unavailable (%s), falling back to hash embedding for demo. "
                "Recall quality is meaningless in this mode; use Docker (Python 3.12) for real BGE.",
                exc,
                extra={"event": "embedding_fallback"},
            )
            _use_hash_fallback = True
            # 预装 numpy（fastembed 已依赖）
            return _hash_embed_sync(texts)
        raise


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
