"""跨模块通用响应模型：列表分页信封与聚合统计。"""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """统一分页信封：所有列表接口的返回形状（前端 pageSchema 与之对应）。"""

    items: list[T]
    total: int = Field(ge=0, description="过滤后的总条数（不受分页影响）")
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0, description="ceil(total / page_size)，0 表示无数据")


class DocumentStats(BaseModel):
    """文档列表顶部计数（全局口径，不随 q/folder 变化）。

    stale 计数不在此处：失效判定依赖 settings 与 ingest_signature 比对（Python 纯函数），
    无法在 SQL 聚合，保持文档行上的 stale 徽标即可。
    """

    total: int
    ready: int
    processing: int  # uploaded + processing
    failed: int
    no_text: int
