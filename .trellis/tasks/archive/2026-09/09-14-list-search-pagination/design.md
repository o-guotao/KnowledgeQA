# Design：列表搜索与分页

## 1. 总体策略

1. **单一返回形状**：所有列表接口一律返回分页信封 `{items,total,page,page_size,pages}`，不做"传 page 才分页"的双形状（避免前端 `Array.isArray()` 分支与两套 zod schema）。这是有意的破坏性契约变更，前后端同版本发布。
2. **搜索在 SQL 层**：`q` 通过 `ILIKE` 子串匹配，方言无关（PostgreSQL / SQLite 均可）。不引入全文索引（后续升级路径见 §6）。
3. **前端一套抽象**：`usePaginatedQuery` + `SearchInput` + `Pagination` 三件套，所有页面复用；聊天页历史消息因流式竞态特殊处理，不走 hook（见 §4.4）。
4. **无数据库迁移**：纯查询层与前端改造，回滚 = revert 代码。

---

## 2. 后端设计

### 2.1 新增：分页信封 schema

`backend/app/schemas/common.py`（新文件）：

```python
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """统一分页信封：所有列表接口的返回形状。"""

    items: list[T]
    total: int = Field(ge=0, description="过滤后的总条数（不受分页影响）")
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0, description="ceil(total / page_size)，0 表示无数据")


class DocumentStats(BaseModel):
    """文档列表顶部计数（全局口径，不随 q/folder 变化）。"""

    total: int
    ready: int
    processing: int  # uploaded + processing
    failed: int
    no_text: int
```

用法：`@router.get("/documents", response_model=Page[DocumentOut])`（pydantic v2 泛型模型，FastAPI 0.115 支持）。

### 2.2 新增：分页与搜索工具

`backend/app/core/pagination.py`（新文件）：

```python
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
MAX_QUERY_LEN = 100


class PageParams:
    """分页查询参数（FastAPI 依赖）：page 从 1 开始，page_size 上限 100。"""

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


def normalize_q(q: str | None) -> str | None:
    """trim + 截断；空串返回 None（= 不过滤）。"""
    term = (q or "").strip()
    return term[:MAX_QUERY_LEN] if term else None


def escape_like(term: str) -> str:
    """转义 LIKE 元字符，使 q 只做字面子串匹配。必须配合 .ilike(..., escape="\\\\")。"""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(q: str) -> str:
    return f"%{escape_like(q)}%"


def make_page(items: list[T], total: int, params: PageParams) -> Page[T]:
    return Page(
        items=items, total=total, page=params.page, page_size=params.page_size,
        pages=(total + params.page_size - 1) // params.page_size,
    )


async def count_rows(db: AsyncSession, stmt: Select) -> int:
    """统计过滤后的总行数：清掉 order_by/limit/offset 后包一层子查询（方言无关）。"""
    sub = stmt.order_by(None).limit(None).offset(None).subquery()
    return (await db.execute(select(func.count()).select_from(sub))).scalar_one()


async def paginate(db: AsyncSession, stmt: Select, params: PageParams) -> tuple[list[Row], int]:
    """先 count 再取当前页。返回原始 Row 列表（调用方自行映射 schema）。"""
    total = await count_rows(db, stmt)
    rows = (await db.execute(stmt.offset(params.offset).limit(params.page_size))).all()
    return list(rows), total
```

设计要点：

- `paginate` 返回 **Row**（不是 ORM 对象），因为团队文档列表是 `select(Document, User.display_name)` 的 join 查询，`.scalars()` 会丢掉 owner 名。单实体查询用 `row[0]`。
- `count_rows` 用子查询而非 `select(func.count()).select_from(Model)`，因为 join / group_by / distinct 查询的 count 语义必须与 items 查询完全一致（否则 `total` 与列表不符）。
- **`PageParams` 用 `__init__` 而非 dataclass**：FastAPI 依赖注入需要函数签名带 `Query(...)` 默认值，dataclass 字段的 `Query` 默认值不会被解析。

### 2.3 稳定排序（分页正确性的前提）

现有排序**没有唯一 tiebreaker**，`created_at` 相同（同一秒批量写入）时 PG/SQLite 返回顺序不确定，翻页会出现**重复或漏项**。所有分页查询必须追加主键作为最后一级排序键：

```python
# 之前
.order_by(Document.folder.asc(), Document.created_at.desc())
# 之后
.order_by(Document.folder.asc(), Document.created_at.desc(), Document.id.desc())
```

`messages` 用 `created_at.desc(), id.desc()`（`Message.id` 若为自增整数则天然有序；若为 UUID 则仅作 tiebreaker）。

### 2.4 逐接口改造

#### `GET /api/documents`（`backend/app/api/documents.py:195`）

```python
@router.get("/documents", response_model=Page[DocumentOut])
async def list_documents(
    folder: str | None = None,
    q: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[DocumentOut]:
    stmt = select(Document).where(Document.user_id == user.id)
    if folder is not None:
        stmt = stmt.where(Document.folder == folder)
    term = normalize_q(q)
    if term is not None:
        pattern = like_pattern(term)
        stmt = stmt.where(
            or_(
                Document.filename.ilike(pattern, escape="\\"),
                cast(Document.tags, String).ilike(pattern, escape="\\"),
            )
        )
    stmt = stmt.order_by(Document.folder.asc(), Document.created_at.desc(), Document.id.desc())
    rows, total = await paginate(db, stmt, params)
    return make_page([_to_out(row[0]) for row in rows], total, params)
```

- **tags 搜索的方言问题**：`tags` 是 `JSON` 列（PG=jsonb，SQLite=JSON 文本）。`cast(Document.tags, String)` 在两端都能转成文本再 `ILIKE`。
  - 已知局限：PG 下文本形如 `["制度", "安全"]`，子串匹配可用；标签内含 `"` 或 `\` 时 JSON 转义会影响匹配（极少见，记录为已知局限）。
- `folder` 保持精确等值（不是子串），语义不变。

#### `GET /api/documents/team`（`documents.py:223`）

同样的 `q`（额外匹配 owner `User.display_name`）+ 分页；count 走同一个 join 子查询：

```python
stmt = (
    select(Document, User.display_name)
    .join(User, Document.user_id == User.id)
    .where(Document.visibility == "team")
)
if term is not None:
    stmt = stmt.where(or_(
        Document.filename.ilike(pattern, escape="\\"),
        cast(Document.tags, String).ilike(pattern, escape="\\"),
        User.display_name.ilike(pattern, escape="\\"),
    ))
stmt = stmt.order_by(Document.created_at.desc(), Document.id.desc())
```

#### `GET /api/documents/stats`（新增）

```python
@router.get("/documents/stats", response_model=DocumentStats)
async def document_stats(db, user) -> DocumentStats:
    rows = (await db.execute(
        select(Document.status, func.count())
        .where(Document.user_id == user.id)
        .group_by(Document.status)
    )).all()
    by_status = {status: n for status, n in rows}
    return DocumentStats(
        total=sum(by_status.values()),
        ready=by_status.get("ready", 0),
        processing=by_status.get("uploaded", 0) + by_status.get("processing", 0),
        failed=by_status.get("failed", 0),
        no_text=by_status.get("no_text", 0),
    )
```

路由注册顺序：**必须在 `GET /documents/{document_id}` 之前**声明，否则 `/documents/stats` 会被 `{document_id}` 匹配成 UUID 解析失败（FastAPI 按声明顺序匹配；`/documents/folders` 已存在同样的先例，紧跟其后声明即可）。

`stale` 计数不放进 stats：stale 判定依赖 `stale_reasons(doc, settings)` 的 Python 纯函数（对比 `ingest_signature`），无法在 SQL 聚合；保持"每个文档行上的 stale 徽标"现状。

#### `GET /api/sessions`（`backend/app/api/sessions.py:27`）

`q` 匹配 `Session.title`，`page_size` 默认 20，排序 `updated_at.desc(), id.desc()`。

#### `GET /api/sessions/{id}/messages`（`sessions.py:77`）

**倒序分页**：`page=1` 是**最新**一页，便于前端"先看到最近对话"：

```python
stmt = (
    select(Message)
    .where(Message.session_id == session_id)
    .order_by(Message.created_at.desc(), Message.id.desc())
)
rows, total = await paginate(db, stmt, params)   # page_size 默认 50
# 流式中断清理：仅作用于本次返回的页（语义与原来一致，范围随分页收窄）
```

`page_size` 默认值对 messages 用 50（`PageParams` 默认 20，此端点显式覆盖：`Query(50, ge=1, le=100)`）。

#### `GET /api/admin/users`（`backend/app/api/admin.py:51`）

`q` 匹配 `username` / `display_name`，新增 `role` 过滤，排序 `created_at.asc(), id.asc()`。

注意：该接口现在**先查全量 users 再查全量 quotas**，再在 Python 侧合并。分页改造后必须先分页 users，再用**当页 user_id 集合**查 quotas，避免拉全量：

```python
rows, total = await paginate(db, stmt, params)
page_user_ids = [row[0].id for row in rows]
quotas = (await db.execute(
    select(Quota).where(Quota.period == period, Quota.user_id.in_(page_user_ids))
)).scalars().all()
```

#### `GET /api/admin/usage/by-user` `by-model`（`admin.py:190` / `admin.py:213`）

聚合查询 + 分页：`q` 分别匹配 `User.username` / `UsageRecord.model`，排序 cost ↓ + 唯一 tiebreaker，`paginate` 对 group_by 查询同样适用（count 用子查询统计分组行数）。

注意 `by-user` 的 `User.username` 是 join 列，过滤写在 `where`（不是 `having`），因为按 username 过滤在分组前即可确定；cost 排序仍在 `order_by`。

#### `GET /api/model-configs`（`backend/app/api/model_configs.py:38`）

`q` 匹配 `name` / `model_name` / `base_url`，排序 `created_at.desc(), id.desc()`。

#### `GET /api/admin/eval/datasets` / `runs`（`backend/app/api/admin_eval.py:50` / `:118`）

- datasets：`q` 匹配 `name`，`source` 过滤。
- runs：**移除硬编码 `.limit(100)`**，改由 `page_size` 控制；`q` 匹配 `name`，保留 `dataset_id` 过滤，新增 `status` 过滤。

#### `GET /api/meta/changelog`（`backend/app/api/meta.py:48`）

内存解析（`CHANGELOG.md`）后过滤 + 切片：

```python
@router.get("/meta/changelog", response_model=Page[dict])
async def meta_changelog(q: str | None = None, params: PageParams = Depends()) -> Page[dict]:
    releases = _parse_changelog(...) if _CHANGELOG_FILE.exists() else []
    term = normalize_q(q)
    if term is not None:
        lowered = term.lower()
        releases = [
            r for r in releases
            if lowered in r["version"].lower()
            or any(lowered in item.lower() for g in r["groups"] for item in g["items"])
        ]
    total = len(releases)
    start = params.offset
    return make_page(releases[start:start + params.page_size], total, params)
```

排序保持解析顺序（新版本在前）。

### 2.5 边界行为

| 场景 | 行为 |
| --- | --- |
| `page=0` / `page_size=0` / `page_size=101` | FastAPI 校验 → 422 |
| `page` 超出 `pages` | `items=[]`，`total`/`pages` 正确（不报错） |
| `q=""` / `q="   "` | 等同不传（`normalize_q` 返回 None） |
| `q` 含 `%` `_` `\` | 字面量匹配（`escape_like`） |
| `q` 超长（>100 字符） | 截断到 100 |
| 无数据 | `{items:[],total:0,page:1,page_size:N,pages:0}` |

---

## 3. 前端设计

### 3.1 zod：分页 schema 工厂

`frontend/src/api/schemas.ts`：

```ts
export function pageSchema<T extends z.ZodTypeAny>(item: T) {
  return z.object({
    items: z.array(item),
    total: z.number().int().nonnegative(),
    page: z.number().int().positive(),
    page_size: z.number().int().positive(),
    pages: z.number().int().nonnegative(),
  });
}

export type PageResult<T> = {
  items: T[]; total: number; page: number; page_size: number; pages: number;
};
```

用法：`get("/documents", pageSchema(DocumentSchema))`。

### 3.2 client：查询串构造

`frontend/src/api/client.ts` 新增（不动现有 `get`/`post`）：

```ts
/** 拼接查询串：跳过 undefined / null / 空串；值为空数组时省略。 */
export function withQuery(
  path: string,
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}
```

### 3.3 hook：`usePaginatedQuery`

`frontend/src/hooks/usePaginatedQuery.ts`（新文件）：

```ts
export interface PageFetchParams { q: string; page: number; page_size: number }

export interface UsePaginatedQueryOptions {
  pageSize?: number;                    // 默认 20
  debounceMs?: number;                  // 默认 300
  enabled?: boolean;                    // false 时不请求（如未激活的 Tab）
  append?: boolean;                     // true = 翻页累加（侧栏「加载更多」）；false = 替换
  extraParams?: Record<string, string | number | undefined>;  // 额外过滤（folder/role/status…）
}

export interface UsePaginatedQueryResult<T> {
  items: T[];
  setItems: React.Dispatch<React.SetStateAction<T[]>>;   // 乐观删除/更新用
  total: number; page: number; pages: number; pageSize: number;
  query: string; setQuery: (value: string) => void;
  setPage: (page: number) => void;
  loading: boolean; error: string | null;
  refresh: () => void;
}

export function usePaginatedQuery<T>(
  fetchPage: (params: PageFetchParams) => Promise<PageResult<T>>,
  options?: UsePaginatedQueryOptions,
): UsePaginatedQueryResult<T>;
```

实现要点（**全部是必须项**）：

1. **`fetchPage` 用 ref 持有**：调用方常传内联箭头函数，若直接进 `useEffect` 依赖会每次渲染都重新请求。用 `fetchPageRef.current = fetchPage` 每次渲染同步，effect 只依赖 `[query, page, pageSize, extraKey, enabled]`。
2. **防抖**：`query` 变化 → 300ms 定时器后 `setPage(1)` 并请求；定时器在下次输入或卸载时清理。防抖期间不清空 `items`（保留上一批结果，避免闪烁）。
3. **竞态守卫**：`requestIdRef.current += 1` 取 `id`，响应回来时 `if (id !== requestIdRef.current) return;` 丢弃过期响应。搜索 + 快速翻页必测。
4. **`extraParams` 变化 → 回第 1 页**：用 `JSON.stringify(extraParams ?? {})` 作为依赖 key，变化时 `setPage(1)`。
5. **`append` 模式**：`page > 1` 时 `setItems(prev => [...prev, ...res.items])`；否则 `setItems(res.items)`。切换 `query`/`extraParams` 时清空并回到 page 1。
6. **卸载安全**：`mountedRef` 防止卸载后 setState。
7. `total` / `pages` 用响应值；`append` 模式下 `total` 仍取服务端 `total`（真实总数）。

### 3.4 组件：搜索框与分页

`frontend/src/components/ui/search-input.tsx`（新文件）：

```tsx
interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
}
```

- 左侧 `lucide-react` `Search` 图标；右侧有值时显示 `X` 清除按钮。
- 内部复用 `ui/input`，纯受控（防抖在 hook 层，组件不持有定时器）。

`frontend/src/components/ui/pagination.tsx`（新文件）：

```tsx
interface PaginationProps {
  page: number;
  pages: number;
  total: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  className?: string;
}
```

- `pages <= 1` 时返回 `null`（单页不显示控件）。
- 布局：左 `共 {total} 条`，右 `上一页` + `第 {page} / {pages} 页` + `下一页`；按钮在边界禁用。
- 用 `ui/button` 的 `outline`/`ghost` 变体，遵循现有深色主题 token（`text-theme-sub` / `border-theme-line`）。

### 3.5 页面接入矩阵

| 页面 | 列表 | 搜索 | 分页 | 备注 |
| --- | --- | --- | --- | --- |
| `DocumentsPage.tsx` | 我的文档 | `SearchInput`（文件名/标签） | `Pagination` pageSize=10 | chips 计数改用 `/documents/stats`；folders 改用 `/documents/folders`；`folder` 走 `extraParams` |
| `DocumentsPage.tsx` | 团队空间 | `SearchInput`（文件名/标签/共享人） | `Pagination` pageSize=10 | 独立 hook 实例，`enabled: tab === "team"` |
| `AdminPage.tsx` | 用户列表 | `SearchInput`（用户名/显示名）+ 角色筛选 | `Pagination` pageSize=10 | 删除/编辑后 `setItems` 乐观移除 + `refresh()` |
| `AdminPage.tsx` | 按用户用量 | `SearchInput`（用户名） | `Pagination` pageSize=10 | |
| `AdminPage.tsx` | 模型用量 | `SearchInput`（模型名） | `Pagination` pageSize=10 | |
| `AdminPage.tsx` | 按日用量 | 不加 | 不加 | **例外**：时间序列，保留 `days=30` |
| `admin/EvalCenterTab.tsx` | 数据集 | `SearchInput`（名称） | `Pagination` pageSize=10 | |
| `admin/EvalCenterTab.tsx` | 评测运行 | `SearchInput`（运行名） | `Pagination` pageSize=10 | 「评测运行总数」卡片改用 `total` |
| `ChatPage.tsx` + `SessionList.tsx` | 会话侧栏 | `SearchInput`（标题） | 累加式「加载更多」pageSize=30 | `append: true` |
| `ChatPage.tsx` | 历史消息 | 不加 | 「加载更早」pageSize=50 | 特殊处理，见 §4.4 |
| `ModelSettingsPage.tsx` | 模型配置 | `SearchInput`（名称/模型/地址） | `Pagination` pageSize=10 | |
| `ChangelogPage.tsx` | 更新日志 | `SearchInput`（版本/条目） | `Pagination` pageSize=5 | |

**`EvalCenterTab` 派生逻辑的兼容性说明**（重要，避免误判为回归）：

- `activeCount`、`doneRuns[0]`（最新完成的 run，图表数据源）、`latestDoneId` 仍从**当前页 items** 派生。
- 安全性依据：后端有并发闸 `EVAL_RUN_BUSY`，同一时刻最多 1 个 `pending/running` run。因此"最新的 done run"之前最多只有 1 条非 done 记录，必然落在 `page=1`（pageSize=10，≥2 即安全）内。**不需要**额外的"最新 run"接口。
- `runs.length`（曾用作总数卡片）改为 `total`。

### 3.6 聊天页：历史消息分页的竞态守卫

`.trellis/spec/frontend/state-management.md` 已记录"乐观流式消息 vs 历史重载"竞态（`turnSessionRef`）。分页必须遵守同一规则：

1. **不用 `usePaginatedQuery`**：`messages` 由 SSE 流式追加 + 乐观写入驱动，hook 的"整体替换"语义会与流式竞态冲突。
2. 状态：`historyPage`（已加载到第几页，`1` = 最新页）、`hasOlder`（`historyPage < pages`）、`loadingOlder`。
3. `activeId` 变化 → 加载 `page=1`：**保持现有 `turnSessionRef` 守卫不变**（`if (turnSessionRef.current === activeId) return;`），响应落地前用 cancelled flag 丢弃过期结果。
4. 「加载更早」→ 请求 `page+1`，结果 `reverse()` 后 **prepend**：

```ts
setMessages((prev) => [...olderAsc, ...prev]);   // 只动头部，不碰正在流式的尾部
```

5. 流式进行中（`turnSessionRef.current === activeId`）**禁用**「加载更早」按钮，从源头避免与流式状态交叉。
6. `page` 只对**服务端历史**计数；本轮乐观消息不参与分页计算。

---

## 4. 兼容性、部署与回滚

### 4.1 契约变更影响面

- 列表接口返回形状由 `[...]` 变为 `{items,total,page,page_size,pages}`。前端**所有**列表调用点必须同批更新（`z.array(X)` → `pageSchema(X)`）。
- 需要同步更新的文档：`.trellis/spec/backend/documents-api.md`、`.trellis/spec/backend/eval-center.md`（若含接口返回形状描述）、`CHANGELOG.md`。
- 无第三方消费者（内部系统），不做双形状过渡。

### 4.2 部署注意（写入 CHANGELOG / 部署说明）

前后端必须**同时**部署。若 CDN 缓存了旧前端包，旧包调用新后端会命中 `SCHEMA_MISMATCH`（前端会明确报"响应数据格式异常"）。部署后需确认前端静态资源已刷新（EdgeOne 静态缓存规则 / 强刷）。

### 4.3 回滚

- 代码回滚（`git revert`）即可，**无数据库迁移**、无数据格式变更。
- 回滚点：后端基础设施（§2.1–2.3）→ 后端接口（§2.4）→ 前端基础设施（§3.1–3.4）→ 前端页面（§3.5）。每段独立可回滚。

---

## 5. 已知取舍

| 取舍 | 说明 |
| --- | --- |
| `ILIKE` 而非全文索引 | 实现简单、方言无关、零迁移；中文场景下 `ILIKE` 子串匹配对"文件名/标签/用户名"这类短字段足够。数据量到十万级 chunk/文档时再上 `pg_trgm` / `tsvector`（届时接口形状不变，只换 `where` 实现）。 |
| tags 用 `cast(..., String)` 匹配 | 避免为方言写分支；代价是含引号/反斜杠的标签匹配可能失准（罕见）。 |
| 分页用 offset/limit | 深翻页性能随 offset 增大而下降。本项目单用户列表规模有限；会话/消息侧栏用"加载更多"累加，天然规避深翻页。到需要时再换游标分页。 |
| `total` 每次都单独 count | 每次列表请求 2 次查询。规模下可接受；如需优化可加缓存或 `COUNT(*) OVER ()` 窗口函数（PG 可用、SQLite 亦支持）。 |
| `pages=0` 表示无数据 | 与 `page=1` 组合语义：无数据时 `page` 仍为 1、`pages` 为 0，前端据此隐藏分页控件。 |
