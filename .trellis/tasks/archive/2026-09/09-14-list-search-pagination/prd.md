# PRD：列表搜索与分页（全系统列表统一）

## 1. 背景

当前系统所有列表接口都返回**裸数组**（`response_model=list[Xxx]`），全部没有 `q` / `page` / `page_size` 参数：

| 接口 | 现状 |
| --- | --- |
| `GET /api/documents` | 仅 `folder` 精确过滤，全量返回 |
| `GET /api/documents/team` | 全量返回（join users 取 owner 名） |
| `GET /api/sessions` | 全量返回 |
| `GET /api/sessions/{id}/messages` | 全量返回（含流式中断清理逻辑） |
| `GET /api/model-configs` | 全量返回 |
| `GET /api/admin/users` | 全量返回 |
| `GET /api/admin/usage/by-user` `by-model` | 仅 `days` 时间窗 |
| `GET /api/admin/eval/datasets` | 全量返回 |
| `GET /api/admin/eval/runs` | **硬编码 `.limit(100)`**（超过 100 条静默截断） |
| `GET /api/meta/changelog` | 全量返回解析结果 |

前端对应地**一次性拉全量 + 本地 `filter`**，没有任何可复用的搜索框 / 分页组件。

问题：
1. 文档、用户、评测运行数量增长后首屏传输与渲染成本线性上升；评测运行记录还会被 100 条硬上限静默截断，用户看不到全部历史。
2. 前端只能"搜到已加载的数据"，没有服务端搜索能力。
3. 每个页面各写一套过滤/渲染逻辑，交互不一致（有的有 chips 过滤，有的没有）。

## 2. 目标

给系统内所有列表统一加上**搜索框**与**分页**，且搜索与分页都在**服务端**完成：

- 后端：列表接口统一新增 `q`（关键词）+ `page` + `page_size`，返回统一分页信封 `{items,total,page,page_size,pages}`。
- 前端：提供可复用的搜索输入、分页控件与数据获取 hook，各列表页接入同一套组件与交互。

## 3. 范围（本次改造的接口）

### 3.1 服务端分页 + 服务端搜索

| 接口 | 搜索字段 `q` | 附加过滤（保留） | 默认排序 |
| --- | --- | --- | --- |
| `GET /api/documents` | `filename` 子串、`tags` 子串 | `folder` | folder ↑, created_at ↓, id ↓ |
| `GET /api/documents/team` | `filename`、`tags`、owner `display_name` | — | created_at ↓, id ↓ |
| `GET /api/admin/users` | `username`、`display_name` | `role` | created_at ↑, id ↑ |
| `GET /api/admin/eval/datasets` | `name` | `source` | created_at ↓, id ↓ |
| `GET /api/admin/eval/runs` | `name` | `dataset_id`、`status` | created_at ↓, id ↓ |
| `GET /api/model-configs` | `name`、`model_name`、`base_url` | — | created_at ↓, id ↓ |
| `GET /api/admin/usage/by-user` | `username` | `days` | cost ↓, user_id ↑ |
| `GET /api/admin/usage/by-model` | `model` | `days` | cost ↓, model ↑ |
| `GET /api/meta/changelog` | 版本号 + 分组条目文本子串 | — | 版本倒序（解析顺序） |

### 3.2 仅服务端分页（不搜索）

| 接口 | 说明 |
| --- | --- |
| `GET /api/sessions` | 会话标题搜索有价值 → **也加 `q`（title 子串）**；侧栏用「加载更多」而非页码 |
| `GET /api/sessions/{id}/messages` | 历史消息按时间序分页，`page=1` 为最新一页；前端「加载更早」prepend。消息内容搜索不在此列（会话内上下文检索不是本次目标） |

### 3.3 明确不做的例外项（已确认，非遗漏）

| 项 | 理由 |
| --- | --- |
| `GET /api/admin/usage/daily` | 按日时间序列（图表 + 趋势条的数据源），行数天然 ≤ `days`（≤365），分页无意义；保留 `days` 窗口 |
| `GET /api/admin/eval/runs/{id}` 详情 `items` | 单次评测 ≤500 题，随详情一次返回；前端详情表已足够 |
| `GET /api/documents/folders` | 非分页列表，是文件夹 chips 的数据源（下拉/枚举语义） |
| `GET /api/admin/eval/runs/{id}/items.csv` | 导出语义 = 全量，不受分页影响 |
| `GET /api/feedback/stats`、`GET /api/quotas/me`、`GET /api/meta/version` | 单体对象，非列表 |

### 3.4 文档列表的统计口径（必须处理，否则功能退化）

`DocumentsPage` 顶部 chips 现有 `全部 / 已入库 / 处理中 / 失败 / 不可检索` 计数，当前由**全量 `docs` 数组**在客户端统计。分页后客户端只有当前页数据，计数会失真。

**要求**：新增 `GET /api/documents/stats`，返回当前用户（或团队空间）的按状态聚合计数，chips 改为读取该接口。计数为**全局口径**（不随 `q` / `folder` 变化），`folder` 过滤结果条数以 `Page.total` 展示。

## 4. 用户可见行为

### 4.1 搜索

- 每个列表顶部有搜索框，占位文案说明搜索字段（如"搜索文件名或标签"）。
- 输入后 **300ms 防抖**触发请求，搜索期间保留上一次结果避免闪烁。
- 搜索词变化时**自动回到第 1 页**。
- 有清除按钮（×）；清空后回到无过滤状态。
- 搜索无结果时展示"没有匹配的…"空态（与"暂无数据"区分）。

### 4.2 分页

- 底部显示：`共 N 条` + 上一页 / `第 x / y 页` / 下一页。
- 只有 1 页时隐藏分页控件（避免噪音）。
- 翻页时列表区域显示加载态，不整页刷新。
- 文档列表的**跨页多选**：已勾选的文档 id 在翻页后保留（`selected` 为 id 集合），"全选"仅作用于**当前页**。
- 会话侧栏与历史消息用**累加式加载**（「加载更多」/「加载更早」），不显示页码。

## 5. 验收标准

### 后端

- [ ] 3.1 / 3.2 表中所有接口支持 `q` / `page` / `page_size`，返回 `{items,total,page,page_size,pages}`。
- [ ] `page < 1` 或 `page_size > 100` 返回 422；`page` 超出范围返回空 `items` 且 `total` / `pages` 正确（不报错）。
- [ ] `q` 中的 `%` `_` `\` 被转义，不会当作通配符（搜索 `100%` 只匹配字面量）。
- [ ] 分页排序稳定（有唯一 tiebreaker），翻页不重复、不遗漏；`total` 与无分页时的一致。
- [ ] `GET /api/admin/eval/runs` 不再有 100 条硬上限（由 `page_size` 控制，可翻到全部历史）。
- [ ] 搜索/分页不影响既有授权隔离（owner / admin / team 可见性规则不变，越权仍 404）。
- [ ] `GET /api/documents/stats` 返回按状态计数，与文档列表全量统计一致。

### 前端

- [ ] 3.1–3.4 涉及的所有列表页均有搜索框与分页控件，行为符合第 4 节。
- [ ] 搜索框输入不触发每字符请求（防抖生效）；快速连续输入/翻页不产生竞态（旧响应不覆盖新结果）。
- [ ] 文档页 chips 计数来自 `stats` 接口，与文档总数一致（不因分页而变小）。
- [ ] 团队空间、模型配置、评测数据集/运行、管理后台用户、用量表、更新日志、会话侧栏均已接入。
- [ ] `npm run build` 与 `npm run lint` 通过。
- [ ] 历史消息分页**不破坏**流式问答：正在流式输出时加载更早的消息不会清掉乐观消息（遵守 `.trellis/spec/frontend/state-management.md` 的竞态规则）。

### 文档

- [ ] `.trellis/spec/backend/documents-api.md` 等 spec 中涉及列表返回形状的段落同步更新。
- [ ] CHANGELOG.md 记录本次契约变更（**列表接口返回形状变更，属破坏性变更**）。

## 6. 约束与风险

1. **契约破坏性变更**：列表接口返回值由裸数组改为分页信封。前后端同仓同版本部署，无第三方消费者，选择"单一返回类型"以避免双形状分支；但必须同步更新所有前端调用点与 spec 文档。
2. **方言兼容**：项目同时支持 PostgreSQL（生产）与 SQLite（本地演示），搜索实现必须方言无关（`tags` 为 `JSON` 列，需 cast 为文本后匹配）。
3. **SQLite 与 PG 的 `ILIKE`**：SQLAlchemy 的 `ilike` 在两端均可用（SQLite 下退化为大小写不敏感的 LIKE）。
4. **聊天页竞态**：历史消息分页与 SSE 流式追加共存，是最容易引入回归的地方，必须有明确的守卫条件。
5. **不做**：向量检索/全文索引级别的搜索（`tsvector` / pg_trgm）；本次是 `ILIKE` 子串匹配，后续可升级（在 design 中记录升级路径）。
