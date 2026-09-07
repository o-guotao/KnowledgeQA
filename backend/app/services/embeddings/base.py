"""Embedding 后端协议：与 model_configs.ProviderConfig 同范式，按配置可切换实现。"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingBackend(Protocol):
    """embedding 后端协议。

    - embed_texts：批量向量化，返回与输入等长的向量列表
    - dim：该后端实际输出维度（用于启动校验与 vector 列匹配）
    - is_semantic：是否有真实语义。False（hash 降级）在生产环境必须被拒绝
    """

    @property
    def dim(self) -> int: ...

    @property
    def is_semantic(self) -> bool: ...

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
