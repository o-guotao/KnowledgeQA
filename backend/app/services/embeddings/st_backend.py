"""sentence-transformers 本地后端（备选）。依赖 torch，体积大，懒加载。

注意：torch 在 Python 3.14 的兼容性需自行验证；fastembed 不可用时此为备选本地方案。
"""
import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


class SentenceTransformersBackend:
    def __init__(self) -> None:
        self._model = None
        settings = get_settings()
        self._model_name = settings.embedding_model
        self._dim = settings.embedding_dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_semantic(self) -> bool:
        return True

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # 懒加载

            logger.info("loading sentence-transformers model %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        return [vec.tolist() for vec in model.encode(texts, convert_to_numpy=True)]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_sync, texts)
