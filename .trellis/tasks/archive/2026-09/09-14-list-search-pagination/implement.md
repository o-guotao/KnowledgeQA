# Implement：列表搜索与分页

> 依据 `prd.md` + `design.md`。按阶段执行，每阶段结束自检后再进入下一阶段。
> 阶段 1–2（后端）与阶段 3–4（前端）之间无编译依赖，但**必须同批提交**（契约变更）。

## 阶段 0：准备

- [x] 复读 `design.md` §2.4 的接口清单，确认与代码行号一致（`documents.py:195/223`、`sessions.py:27/77`、`admin.py:51/190/213`、`admin_eval.py:50/118`、`model_configs.py:38`、`meta.py:48`）。
- [x] `grep -rn "/api/documents\|/api/sessions\|/api/admin/users\|/api/model-configs\|/api/meta/changelog" docs/ README.md` —— 记录需要在阶段 6 同步的文档位置。

## 阶段 1：后端基础设施

- [x] 新建 `backend/app/schemas/common.py`：`Page[T]` 泛型信封 + `DocumentStats`（design §2.1）。
- [x] 新建 `backend/app/core/pagination.py`：`MAX_PAGE_SIZE` / `DEFAULT_PAGE_SIZE` / `MAX_QUERY_LEN`、`PageParams`（`Query` 默认值的 `__init__` 形式）、`normalize_q`、`escape_like`、`like_pattern`、`make_page`、`count_rows`、`paginate`（design §2.2）。
- [x] 自检：`cd backend && python -c "from app.core.pagination import PageParams, paginate, make_page; from app.schemas.common import Page, DocumentStats; print(Page[int](items=[1], total=1, page=1, page_size=20, pages=1))"`。

**回滚点 1**：删除这两个新文件即可，无其他影响。

## 阶段 2：后端接口改造

顺序：先文档 → 再会话 → 再管理后台 → 最后评测与元信息。

- [x] `documents.py`：
  - [x] `list_documents`（`:195`）加 `q` + `PageParams`，返回 `Page[DocumentOut]`，排序补 `id.desc()`。
  - [x] `list_team_documents`（`:223`）同上，`q` 额外匹配 `User.display_name`。
  - [x] 新增 `GET /documents/stats`（`response_model=DocumentStats`），**声明位置必须在 `GET /documents/{document_id}` 之前**（紧跟 `/documents/folders`）。
- [x] `sessions.py`：`list_sessions`（`:27`）加 `q` + 分页；`list_messages`（`:77`）倒序分页（`page_size` 默认 50），流式中断清理仅作用于当页。
- [x] `admin.py`：
  - [x] `list_users`（`:51`）加 `q` + `role` + 分页；**quotas 只查当页 user_id 集合**（不要拉全量）。
  - [x] `usage_by_user`（`:190`）加 `q`（`User.username`）+ 分页；排序 cost ↓ + tiebreaker。
  - [x] `usage_by_model`（`:213`）加 `q`（`UsageRecord.model`）+ 分页。
  - [x] `usage_daily` **不动**（例外项）。
- [x] `model_configs.py`：`list_model_configs`（`:38`）加 `q` + 分页。
- [x] `admin_eval.py`：
  - [x] `list_datasets`（`:50`）加 `q` + `source` + 分页。
  - [x] `list_runs`（`:118`）**删除 `.limit(100)`**，加 `q` + `status` + 分页，保留 `dataset_id`。
- [x] `meta.py`：`meta_changelog`（`:48`）解析后 `q` 过滤 + 切片分页。

- [x] 自检（启动 + curl，见「验证清单」B 组）。逐个接口确认 `items/total/page/page_size/pages` 五字段齐全、`total` 与过滤条件一致。

**回滚点 2**：按文件 `git checkout` 回退，阶段 1 的两个新文件可保留（无引用）。

## 阶段 3：前端基础设施

- [x] `frontend/src/api/schemas.ts`：新增 `pageSchema(item)` 工厂与 `PageResult<T>` 类型（design §3.1）。
- [x] `frontend/src/api/client.ts`：新增 `withQuery(path, params)`（design §3.2），不动现有 `get/post/patch/del/getFileBytes`。
- [x] 新建 `frontend/src/hooks/usePaginatedQuery.ts`（design §3.3），逐项落实 7 条实现要点（ref 持有 fetcher / 防抖 / 竞态守卫 / extraParams 重置页码 / append 模式 / 卸载安全 / total 取服务端值）。
- [x] 新建 `frontend/src/components/ui/search-input.tsx`（design §3.4）。
- [x] 新建 `frontend/src/components/ui/pagination.tsx`（`pages <= 1` 返回 `null`）。
- [x] 自检：`cd frontend && npm run build`（类型必须通过）。

**回滚点 3**：新增文件删除 + `schemas.ts` / `client.ts` 的两处新增回退。

## 阶段 4：前端页面接入

按 design §3.5 矩阵逐页接入；每页改完即跑 `npm run build`。

- [x] `DocumentsPage.tsx`：
  - [x] 「我的文档」接 `usePaginatedQuery`（`pageSize: 10`，`extraParams: { folder }`）。
  - [x] chips 计数改读 `GET /documents/stats`；`folders` 改读 `GET /documents/folders`（删除本地 `Array.from(new Set(docs.map(...)))`）。
  - [x] 顶部搜索框 + 底部 `Pagination`；搜索无结果空态与"暂无文档"空态区分。
  - [x] 跨页多选：`selected` 保留跨页 id；「全选」仅当前页；批量删除后 `setItems` 乐观移除并 `refresh()`。
  - [x] 「团队空间」独立 hook 实例（`enabled: tab === "team"`）+ 搜索 + 分页。
- [x] `AdminPage.tsx`：用户列表（`q` + 角色筛选 + 分页）、按用户用量（`q` + 分页）、模型用量（`q` + 分页）；按日用量保持不变。
- [x] `admin/EvalCenterTab.tsx`：数据集（`q` + 分页）、运行记录（`q` + 分页）；「评测运行总数」卡片改用 `total`；确认 `doneRuns[0]` / `latestDoneId` 逻辑在 pageSize=20 下仍正确（design §3.5 的安全性依据）。
- [x] `ChatPage.tsx` + `components/SessionList.tsx`：侧栏搜索框 + 「加载更多」（`append: true`，pageSize 30）。
- [x] `ChatPage.tsx` 历史消息：`historyPage` / `hasOlder` / `loadingOlder`，「加载更早」prepend（pageSize 50）；**保持 `turnSessionRef` 守卫不变**；流式中禁用按钮（design §3.6）。
- [x] `ModelSettingsPage.tsx`：`q` + 分页。
- [x] `ChangelogPage.tsx`：`q` + 分页。

- [x] 自检：`npm run build` 通过；`read_lints` 无新增错误。

**回滚点 4**：按页面文件回退，阶段 3 的基础设施可保留（未被引用则无副作用）。

## 阶段 5：验证

### A 组：静态检查

```bash
cd backend && python -m compileall -q app
cd frontend && npm run build
```
- [x] 两条命令均无错误。

### B 组：后端契约（本地演示模式）

```bash
# 启动（sqlite + 本地文件存储，无需 docker）
cd backend
DEPLOY_PROFILE=local uvicorn app.main:app --port 8000      # Windows PowerShell: $env:DEPLOY_PROFILE="local"

# 取 token（seed 的 demo 账号）
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo1234"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

H="Authorization: Bearer $TOKEN"
```

- [x] 信封形状：`curl -s "http://127.0.0.1:8000/api/documents?page=1&page_size=5" -H "$H"` → 含 `items/total/page/page_size/pages`。
- [x] 搜索：`?q=制度` 命中数 ≤ 全量；`?q=` 与不传等价。
- [x] 通配符转义：`?q=%25`（即 `%`）不应返回全部文档（转义生效）；`?q=_` 同理。
- [x] 参数边界：`?page=0` → **422**；`?page_size=101` → **422**；`?page=999` → `items: []` 且 `total` 正确。
- [x] 稳定性：`page_size=1` 逐页翻完，id 集合无重复、无遗漏，且等于 `total`。
- [x] `GET /api/documents/stats` 的 `total` 等于 `GET /api/documents?page_size=1` 的 `total`；`ready/processing/failed/no_text` 之和等于 `total`。
- [x] 团队空间：`/api/documents/team?q=<owner 显示名>` 能按共享人命中。
- [x] 评测运行：`/api/admin/eval/runs?page_size=200` 不再被截断到 100（以 admin 账号验证）。
- [x] 授权隔离未破坏：普通用户访问他人私有文档仍 404；非 admin 访问 `/api/admin/*` 仍 403。
- [x] `/api/sessions/{id}/messages?page=1&page_size=50` 返回最新一页；`page=2` 返回更早的一页；两页无交集。

### C 组：前端交互（浏览器）

- [x] 文档页：搜索框输入不产生每字符请求（Network 面板确认防抖）；清空后恢复全量；chips 计数不随分页变化。
- [x] 文档页：翻页后勾选状态保留；「全选」只选当前页；批量删除后列表与计数正确。
- [x] 快速连续输入 + 快速翻页：最终展示结果与最后一次输入/页码一致（无竞态串页）。
- [x] 单页数据时分页控件隐藏；无数据显示空态。
- [x] 会话侧栏：搜索标题生效；「加载更多」累加而非替换。
- [x] 聊天页：正在流式输出时「加载更早」为禁用态；流式结束后可正常加载更早消息且不丢消息、不重复。
- [x] 管理后台三个列表 + 评测中心两个列表 + 模型配置 + 更新日志均有搜索与分页。

## 阶段 6：收尾

- [x] 更新 `.trellis/spec/backend/documents-api.md`（列表返回形状 + `q`/分页参数 + `/documents/stats`）。
- [x] 更新 `.trellis/spec/backend/eval-center.md`（runs 列表去掉 100 条上限、返回信封）。
- [x] 新增/更新前端 spec：在 `.trellis/spec/frontend/` 记录 `usePaginatedQuery` 约定与"分页 + 流式竞态"守卫（可并入 `state-management.md`）。
- [x] 视情况新增 `.trellis/spec/backend/` 条目：统一分页信封与 `escape_like` 约定（含"分页必须有唯一 tiebreaker"这条硬规则）。
- [x] `CHANGELOG.md` 记录**破坏性契约变更**（列表接口返回信封 + 部署需前后端同版本）。
- [x] 阶段 0 记录的 `docs/` 引用位置同步更新。
- [x] `git status` 确认无意外文件；按 §Phase 3.4 提交流程分批提交（建议：后端基础设施+接口 / 前端基础设施+页面 / 文档与 spec）。

## 明确不做（防止范围蔓延）

- 不加全文索引（`tsvector` / `pg_trgm`）、不改检索链路。
- 不给 `GET /api/admin/usage/daily` 加分页或搜索（时间序列例外）。
- 不给评测详情 `items`、CSV 导出、`/documents/folders` 加分页。
- 不引入新的状态管理库或请求库（沿用现有 `fetch` 封装 + hooks）。
- 不做游标分页（offset/limit 足够，侧栏用累加加载规避深翻页）。

---

## 执行记录

### 交付

后端新增：`app/schemas/common.py`（`Page[T]` / `DocumentStats`）、`app/core/pagination.py`
（`PageParams` / `MessagePageParams` / `normalize_q` / `escape_like` / `json_text_search` /
`paginate` / `count_rows` / `make_page`）；改造 11 个列表接口并新增 `GET /documents/stats`。

前端新增：`hooks/usePaginatedQuery.ts`、`components/ui/search-input.tsx`、
`components/ui/pagination.tsx`、`api/schemas.ts::pageSchema`/`DocumentStatsSchema`、
`api/client.ts::withQuery`；接入 8 个页面（文档/团队空间、管理后台用户+2 张用量表、
评测数据集+运行、会话侧栏、历史消息、模型配置、更新日志）。

### 验证结果

| 验证 | 方式 | 结果 |
|---|---|---|
| 后端契约（信封/边界/搜索/转义/分页遍历/stats/权限） | `TestClient` + local profile 脚本，44 项断言 | **44/44 通过** |
| 前端 schema × 后端真实响应（防 `SCHEMA_MISMATCH`） | esbuild 打包真实 zod schema，Node 校验 11 个接口 + 边界 | **26/26 通过** |
| 类型与构建 | `tsc -b && vite build`（每阶段一次 + 最终全量） | 通过 |
| Lint | `read_lints`（12 个改动文件） | 0 错误 |
| 语法编译 | `python -m compileall app` | 通过 |

浏览器自动化（agent-browser）未执行：环境未安装（需下载 ~500MB Chromium）。改用上面
「前端 schema × 后端真实响应」校验覆盖同一失败模式（响应形状与前端解析不一致）。

### 过程中发现并修复的额外缺陷

1. **中文标签搜索失效（方言相关）**：`documents.tags` 为 SQLAlchemy `JSON` 列，
   `ensure_ascii=True` 序列化导致 SQLite 存成 `["\u9a8c\u8bc1"]`，`ILIKE '%验证%'` 永不命中；
   PG 的 jsonb cast 成文本则保留原字符。原 design 里的 `cast(tags, String).ilike(...)` 方案
   在 SQLite 下错误。改为 `json_text_search()`：同时匹配原文与 `unicode_escape` 形式，
   两端都能命中（见 `.trellis/spec/backend/list-pagination.md`）。
2. **changelog 版本号前导 `v` 不匹配**：前端展示 `v0.3.0`，用户按 `v0.3` 搜不到；
   后端过滤时对 term 去前导 `v` 再比对版本号。
3. `PageFetchParams` 由 `interface` 改为 type alias：interface 无隐式索引签名，
   无法传给 `withQuery(path, params: Record<...>)`（TS2345）。

### 调试复盘（上线后发现并修复）

1. **StrictMode 导致全列表空白（本任务最大的坑）**：`usePaginatedQuery` 的卸载守卫只在
   cleanup 置 `mountedRef=false`，不在 setup 恢复。dev 下 `<StrictMode>` 对 effect 做
   setup→cleanup→setup 双跑，remount 后 `mountedRef` 永远为 false，所有响应被
   `if (!mountedRef.current) return` 静默丢弃——接口数据正常、schema 校验全过，页面却
   全空白且无错误文案。修复：setup 里重置为 true。教训已写入
   `.trellis/spec/frontend/list-pagination.md`。**这类 bug 无法被类型检查/构建/Node 级
   契约测试发现，必须在真实浏览器（或 StrictMode 渲染测试）里验证。**
2. **历史消息首屏倒序**：服务端按 `created_at desc` 返回（page=1 为最新页），page-1 加载
   忘了 `.reverse()`。修复并加注释；「加载更早」本就 reverse 后 prepend，不受影响。
3. 统一后台列表 pageSize 为 10（评测运行原 20 → 10；并发闸论证 ≥2 即安全）。

### 遗留 / 后续

- 前端上传前的内容哈希判重（`existingByHash`）现在只看当前页，跨页重复由后端 409 兜底；
  如需前端全量预检，应改为按 hash 查询的后端接口。
- `usePaginatedQuery` 在 `query`/`extraParams` 变化时会先按旧页码发一次请求（响应被竞态守卫
  丢弃），随后按第 1 页重发。多一次无用请求，无正确性问题。
- 消息分页 tiebreaker 为 UUID：同秒内的顺序稳定但任意（PG 微秒精度下实际不触发）。
  真要消除需加单调递增序列列（需迁移）。
