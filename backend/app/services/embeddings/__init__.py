"""Embedding 后端工厂与启动校验。

后端选择（EMBEDDING_BACKEND）：
- fastembed：本地 BGE（生产 Docker 默认，需 onnxruntime 可用）
- openai：OpenAI 兼容 embedding API（DeepSeek 无 embedding 时的替代）
- sentence_transformers：本地 torch（备选，体积大）
- hash：无语义降级，仅开发演示（生产禁止）

fastembed 懒加载——构造不暴露 onnxruntime 兼容性，真实可用性由
verify_embedding_ready() 实际调用一次 embed 判定并执行降级/fail-fast。
"""
import logging

from app.config import get_settings
from app.services.embeddings.base import EmbeddingBackend

logger = logging.getLogger(__name__)

_backend: EmbeddingBackend | None = None


def _construct(name: str) -> EmbeddingBackend:
    if name == "openai":
        from app.services.embeddings.openai_backend import OpenAIEmbeddingBackend
        return OpenAIEmbeddingBackend()
    if name == "sentence_transformers":
        from app.services.embeddings.st_backend import SentenceTransformersBackend
        return SentenceTransformersBackend()
    if name == "hash":
        from app.services.embeddings.hash_backend import HashEmbeddingBackend
        return HashEmbeddingBackend()
    from app.services.embeddings.fastembed_backend import FastEmbedBackend
    return FastEmbedBackend()


def get_embedding_backend() -> EmbeddingBackend:
    """按配置返回 embedding 后端（单例）。"""
    global _backend
    if _backend is None:
        _backend = _construct(get_settings().embedding_backend.lower())
        logger.info(
            "embedding backend constructed: %s (dim=%d, semantic=%s)",
            type(_backend).__name__, _backend.dim, _backend.is_semantic,
        )
    return _backend


def _allow_hash_downgrade() -> bool:
    settings = get_settings()
    return settings.allow_hash_embedding and settings.environment != "production"


async def verify_embedding_ready() -> tuple[bool, str]:
    """启动校验：真实调用一次 embed，校验可用性与维度，执行降级或 fail-fast。

    返回 (ok, message)。生产环境 ok=False 时调用方必须终止启动。
    """
    global _backend
    settings = get_settings()
    backend = get_embedding_backend()

    try:
        sample = await backend.embed_texts(["维度校验"])
        actual = len(sample[0])
    except Exception as exc:
        # 真实调用失败（如 fastembed 在 Python 3.14 onnxruntime DLL 崩溃）
        if settings.embedding_backend.lower() == "fastembed" and _allow_hash_downgrade():
            from app.services.embeddings.hash_backend import HashEmbeddingBackend
            _backend = HashEmbeddingBackend()
            logger.warning(
                "fastembed unavailable (%s), downgraded to hash embedding (development only)",
                exc, extra={"event": "embedding_hash_downgrade"},
            )
            return True, f"embedding degraded to hash (dev only): {exc}"
        return False, f"embedding 后端实际调用失败：{exc}"

    if actual != settings.embedding_dim:
        return False, (
            f"embedding 维度不匹配：后端输出 {actual} 维，"
            f"EMBEDDING_DIM={settings.embedding_dim}，迁移列为 vector(512)。"
        )

    # 非语义后端（hash）在生产/禁用降级时拒绝
    if not backend.is_semantic and not _allow_hash_downgrade():
        return False, (
            "当前 embedding 为无语义 hash 降级，但处于 production 或已禁用降级。"
            "hash 召回等于随机，禁止进生产。请配置真实 embedding 后端。"
        )

    return True, f"embedding ok: {type(backend).__name__} dim={actual} semantic={backend.is_semantic}"
