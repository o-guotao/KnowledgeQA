# 管理后台（用户 / 用量 / 成本）

## Goal

为 admin 提供独立管理后台：用户 CRUD、用量看板（按日 / 按用户 / 按模型）、成本报表。数据来源于每次 LLM 调用明细（新增 `usage_records` 表）+ 现有 `quotas` / `users`。仅 `role=admin` 可访问，普通用户一律 403。

## Requirements

1. **调用明细落库**：每次 LLM 调用在 chat 流 usage 事件处写一条 `usage_records`（user_id / session_id / model / prompt_tokens / completion_tokens / cost_cny / trace_id / created_at）。postgres 走 alembic 迁移，sqlite 走 `create_all`。
2. **admin 鉴权**：新增 `require_admin` 依赖（`role=="admin"` 否则 403）；`/admin` 前缀全部端点强制套用。
3. **用户 CRUD**：列表（含当月用量与配额）、新建、编辑（display_name / role / 配额上限 / 重置密码）、删除。删除保护：不能删自己、不能删最后一个 admin。
4. **用量看板**：按日聚合（近 N 天：日期 / tokens / 成本 / 调用次数）、按用户、按模型三个维度。
5. **成本报表**：按日成本 + 按模型成本（复用聚合数据，口径与 quotas 一致）。
6. **前端 AdminPage**：仅 admin 可见导航入口与 `/admin` 路由；用量图表 + 用户管理表格；非 admin 访问被拦。

## Acceptance Criteria

- [ ] 普通用户调 `/admin/*` → 403；admin → 200。
- [ ] 发起一次对话后，`usage_records` 新增对应明细（model / token / cost 正确）。
- [ ] 用户列表展示各用户当月用量与配额；可新建 / 编辑 / 删除用户，删除保护生效。
- [ ] 用量看板按日 / 按用户 / 按模型三视图数据与实际调用一致。
- [ ] 成本随调用累计，报表数字与 quotas 口径一致。
- [ ] 非 admin 登录前端无后台入口；直接访问 `/admin` 被拦截重定向。

## Out of Scope

- 导出 CSV、定时报表、按会话 / 按文档维度、数据大屏美化、引入图表库。

## Notes

- 复杂全栈任务；遵循"无新组件优先"，不引入图表库 / 新中间件。
- 前置：Python 3.12 环境（真向量）另立任务，与本后台功能解耦。
