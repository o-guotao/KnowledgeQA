"""fastembed 本地 BGE embedding（ONNX，CPU 可跑）。生产 Docker(Python 3.12) 默认后端。

fastembed 为重量级依赖，懒加载，保证仅导入契约层时无需安装。
注意：onnxruntime 在 Python 3.14 下 DLL 加载失败——
该后端在非 3.12 环境加载会抛错，由工厂按配置切换到其他后端。
"""
import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


class FastEmbedBackend:
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
            from fastembed import TextEmbedding  # 懒加载

            logger.info("loading fastembed model %s", self._model_name)
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        return [vec.tolist() for vec in model.embed(texts)]

    async def embed_texts(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            results.extend(await asyncio.to_thread(self._embed_sync, batch))
        return results
