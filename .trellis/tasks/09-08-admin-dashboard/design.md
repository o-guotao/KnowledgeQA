# 管理后台 — 技术设计

## 结论先行

- 新增 `usage_records` 调用明细表（每次调用一行），与 `quotas`（月度配额累计）并存：`quotas` 管限额，`usage_records` 管看板 / 报表。
- 不引入图表库：前端用 tailwind 表格 + CSS 条形图渲染。
- `/admin` 端点集中在新的 `api/admin.py`，统一 `require_admin`。

## 后端改动

### 数据层
- `models/usage_record.py`（新建）：`id` UUID pk、`user_id` FK→users、`session_id` UUID nullable、`model` String(64)、`prompt_tokens` int、`completion_tokens` int、`cost_cny` Float、`trace_id` String(32)、`created_at` DateTime server_default now()。索引 `(user_id, created_at)`、`(model)`、`(created_at)`。
- `models/__init__.py` 注册（sqlite `create_all` 依赖 `import app.models`）。
- `alembic/versions/0011_usage_records.py`（postgres 迁移，含索引）。

### 明细写入
- `chat.py` usage 事件处（现约 174-176 行 `accumulate_usage` 同事务）追加写一条 `UsageRecord`：`model=provider.model_name`、`session_id=body.session_id`、`trace_id=trace_id`、`p/c/cost_cny_round`。

### 鉴权
- `core/security.py` 加 `require_admin`：在 `get_current_user` 之后判 `role=="admin"`，否则 `AppError("FORBIDDEN","需要管理员权限",403)`。

### 管理端点 `api/admin.py`（前缀 `/admin`，`dependencies=[Depends(require_admin)]`）
- `GET /admin/users`：join 当月 quotas → `[{id,username,display_name,role,created_at,month:{prompt,completion,cost,limit}}]`。
- `POST /admin/users` `{username,password,display_name,role}` → 201；用户名重复 409。
- `PATCH /admin/users/{id}` `{display_name?,role?,limit_tokens?,password?}` 局部更新（limit 写当月 quota 行）。
- `DELETE /admin/users/{id}`：保护（自删 / 最后一个 admin → 400）；级联清理关联数据。
- `GET /admin/usage/daily?days=30`：`func.date(created_at)` 分组 → `[{date,calls,prompt,completion,cost}]`。
- `GET /admin/usage/by-user?days=30`：按 user 分组 join username → `[{user_id,username,calls,tokens,cost}]`。
- `GET /admin/usage/by-model?days=30`：按 model 分组 → `[{model,calls,tokens,cost}]`。
- 日期分组用 `func.date(created_at)`，sqlite 与 postgres 均支持。

### schemas
- `schemas/admin.py`：`AdminUserOut` / `AdminUserCreate` / `AdminUserPatch` / `DailyUsage` / `UserUsage` / `ModelUsage`。

## 前端改动

- `api/schemas.ts`：admin 相关 zod schema。
- `pages/AdminPage.tsx`（新建）：
  - 顶部统计卡（近 30 天 tokens / 成本 / 调用数）。
  - 按日用量 CSS 条形图。
  - 按模型 / 按用户两个表格。
  - 用户管理表格 + 新建 / 编辑 / 删除。
- `App.tsx` 加 `/admin` 路由（`RequireAuth` 包裹）。
- 导航：仅 `user.role=="admin"` 渲染"管理后台"入口。

## 明确不做

- 图表库、CSV 导出、定时任务、按会话 / 文档维度、细粒度 RBAC。

## 风险

- `usage_records` 每调用一行：演示量级无忧；生产归档留作后续（Out of Scope）。
- 删除用户级联：需一并清理 sessions / messages / quotas / usage_records，或 FK `ondelete`。
- 日期分组方言：统一 `func.date(created_at)` 兼容 sqlite / postgres。
