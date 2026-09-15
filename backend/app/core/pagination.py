"""列表分页与搜索工具：统一 page/page_size 参数、分页信封构造、方言无关的 ILIKE 搜索。

所有列表接口共用本模块，避免每个端点各写一套 offset/limit 与 count 逻辑。
"""
from typing import Any, TypeVar

from fastapi import Query
from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import Page

T = TypeVar("T")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
# 历史消息一屏需要更多条（倒序分页，page=1 为最新一页）
DEFAULT_MESSAGE_PAGE_SIZE = 50
MAX_QUERY_LEN = 100
LIKE_ESCAPE = "\\"


class PageParams:
    """分页查询参数（FastAPI 依赖）：page 从 1 开始，page_size 上限 100。

    用显式 __init__ 而非 dataclass：FastAPI 依赖注入需要函数签名上带 Query(...) 默认值。
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class MessagePageParams(PageParams):
    """历史消息分页参数：一屏默认 50 条（倒序分页，page=1 为最新一页）。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始（1 = 最新一页）"),
        page_size: int = Query(
            DEFAULT_MESSAGE_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"
        ),
    ) -> None:
        super().__init__(page=page, page_size=page_size)


def normalize_q(q: str | None) -> str | None:
    """trim + 截断；空串返回 None（等同不传 = 不过滤）。"""
    term = (q or "").strip()
    return term[:MAX_QUERY_LEN] if term else None


def escape_like(term: str) -> str:
    """转义 LIKE 元字符，使 q 只做字面子串匹配。

    必须配合 `.ilike(pattern, escape=LIKE_ESCAPE)` 使用，否则转义符不生效。
    """
    return (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def like_pattern(q: str) -> str:
    """把已 normalize 的搜索词包成 %term% 模式（内部完成转义）。"""
    return f"%{escape_like(q)}%"


def json_text_search(column: ColumnElement[Any], term: str) -> ColumnElement[bool]:
    """JSON 列（如 documents.tags）的文本子串匹配条件，跨方言可用。

    **坑**：SQLAlchemy 的 JSON 类型序列化时 `ensure_ascii=True`，所以 SQLite 里中文标签
    实际存成 `["\\u9a8c\\u8bc1"]`（转义形式），`LIKE '%验证%'` 永远不命中；而 PostgreSQL
    的 jsonb 经 cast 成文本后保留原字符，`ILIKE '%验证%'` 能命中。方言行为不一致。

    因此同时匹配「原文字面量」与「unicode 转义形式」两种模式：
    - SQLite：命中转义形式
    - PostgreSQL：命中原文形式（转义形式不匹配，无害）
    """
    patterns = {like_pattern(term)}
    escaped = term.encode("unicode_escape").decode("ascii")
    if escaped != term:
        patterns.add(like_pattern(escaped))
    return or_(*(column.ilike(pattern, escape=LIKE_ESCAPE) for pattern in sorted(patterns)))


def make_page(items: list[T], total: int, params: PageParams) -> Page[T]:
    """构造分页信封；pages 向上取整，0 表示无数据。"""
    return Page(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        pages=(total + params.page_size - 1) // params.page_size,
    )


async def count_rows(db: AsyncSession, stmt: Select) -> int:
    """统计过滤后的总行数。

    清掉 order_by/limit/offset 后包一层子查询，使 join / group_by / distinct 查询的
    count 语义与 items 查询完全一致（直接 count(Model) 会在 join 后算错）。
    """
    sub = stmt.order_by(None).limit(None).offset(None).subquery()
    return int((await db.execute(select(func.count()).select_from(sub))).scalar_one())


async def paginate(db: AsyncSession, stmt: Select, params: PageParams) -> tuple[list[Row[Any]], int]:
    """先 count 再取当前页，返回原始 Row 列表（调用方自行映射 schema）。

    返回 Row 而非 ORM 对象：团队文档列表是 select(Document, User.display_name) 的 join
    查询，.scalars() 会丢掉 owner 名。单实体查询取 row[0]。
    """
    total = await count_rows(db, stmt)
    rows = (await db.execute(stmt.offset(params.offset).limit(params.page_size))).all()
    return list(rows), total
