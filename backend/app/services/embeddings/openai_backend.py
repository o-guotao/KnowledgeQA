"""OpenAI 兼容 embedding API 后端（text-embedding-3 或通义 text-embedding 等兼容端点）。

DeepSeek 无 embedding API——本后端让用户可配 OpenAI/阿里通义/其他兼容端点做向量化。
配置：OPENAI_EMBEDDING_BASE_URL / OPENAI_EMBEDDING_API_KEY / OPENAI_EMBEDDING_MODEL。
"""
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingBackend:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.openai_embedding_base_url.rstrip("/")
        self._api_key = settings.openai_embedding_api_key
        self._model = settings.openai_embedding_model
        self._dim = settings.embedding_dim
        self._timeout = httpx.Timeout(60.0, connect=10.0)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_semantic(self) -> bool:
        return True

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._api_key:
            raise RuntimeError("OpenAI embedding 后端未配置 OPENAI_EMBEDDING_API_KEY")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
            if response.status_code != 200:
                raise RuntimeError(f"embedding API 返回 {response.status_code}")
            data = response.json()
        # 按 index 排序对齐输入顺序
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
