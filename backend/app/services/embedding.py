"""embedding 公共接口（薄壳）：委托给 embeddings 抽象层，保持原调用签名不变。

实现细节（后端选择/降级/校验）见 services/embeddings/。
调用方（worker/chat.py）无需改动——embed_texts/embed_query/verify_dimension 签名兼容。
"""
from app.services.embeddings import get_embedding_backend, verify_embedding_ready


async def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """批量向量化。batch_size 由具体后端内部处理（fastembed 分批，API 后端可整批）。"""
    if not texts:
        return []
    return await get_embedding_backend().embed_texts(texts)


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text]))[0]


async def verify_dimension() -> int:
    """启动校验：后端可用且维度匹配。失败抛 RuntimeError（供 startup fail fast 判断）。"""
    ok, message = await verify_embedding_ready()
    if not ok:
        raise RuntimeError(message)
    return get_embedding_backend().dim
