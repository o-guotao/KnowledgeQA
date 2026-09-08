# 管理后台 — 执行计划

按序实施，每步后自检。参照 `design.md` 契约（表结构 / 端点 / 错误码）。

## 1. 后端：usage_records 模型 + 迁移 + 注册
- `backend/app/models/usage_record.py`、`models/__init__.py` 注册、`alembic/versions/0011_usage_records.py`。
- 验证：sqlite 启动 `create_all` 见表；postgres `alembic upgrade head` 见表与索引。

## 2. 后端：require_admin + schemas
- `core/security.py` 加 `require_admin`；`schemas/admin.py`。
- 验证：普通用户调 `/admin/users` → 403；admin → 200。

## 3. 后端：admin 用户 CRUD
- `api/admin.py` users 列表 / 新建 / 编辑 / 删除（含保护）；`api/__init__.py` 注册 router。
- 验证：curl 增删改查；删自己 / 最后 admin → 400；用户名重复 → 409。

## 4. 后端：chat 写 usage 明细 + 用量聚合端点
- `chat.py` usage 事件写 `UsageRecord`；`admin.py` daily / by-user / by-model。
- 验证：发起对话 → `usage_records` 有行且字段正确；三聚合端点数据与实际一致。

## 5. 前端：schema + AdminPage + 路由 + 导航
- `api/schemas.ts`、`pages/AdminPage.tsx`、`App.tsx` 路由、admin 导航入口。
- 验证：`npm run build` 通过；admin 登录见看板与用户管理；普通用户无入口且 `/admin` 被拦。

## 6. Review Gate
- 对照 `prd.md` acceptance 全绿；postgres 迁移 `down` 可回滚验证一次（功能验收后）。

## 风险文件 / 回滚点
- `chat.py`（写明细，勿影响流式主流程与费用口径）、`models/__init__.py`、`App.tsx`。
