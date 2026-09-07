"""hash 降级后端：无语义的确定性向量，仅开发演示跑通链路。

is_semantic=False——生产环境（ENVIRONMENT=production 且 ALLOW_HASH_EMBEDDING=false）
启动校验必须拒绝此后端，否则召回等于随机。
"""
import hashlib

import numpy as np

from app.config import get_settings


class HashEmbeddingBackend:
    def __init__(self) -> None:
        self._dim = get_settings().embedding_dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_semantic(self) -> bool:
        return False

    def _hash_embed(self, text: str) -> list[float]:
        vec = np.zeros(self._dim, dtype=np.float32)
        for i in range(0, self._dim, 8):
            h = hashlib.sha256(f"{i}:{text}".encode()).digest()
            for j, b in enumerate(h):
                if i + j < self._dim:
                    vec[i + j] = (b - 128) / 128.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]
