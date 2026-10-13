---
name: user-registration
overview: 为内部知识库系统增加开放注册功能：后端新增 POST /auth/register 接口（校验用户名唯一、密码强度，role 固定 user），前端新增注册页 /register 并在登录页加入口，注册成功后跳回登录页手动登录。用户手动实施，计划给出每个文件的具体改动内容。
design:
  architecture:
    framework: react
    component: shadcn
  styleKeywords:
    - 深色企业风
    - 沉稳深墨底
    - 品牌光晕
    - 精细边框卡片
  fontSystem:
    fontFamily: PingFang-SC
    heading:
      size: 32px
      weight: 600
    subheading:
      size: 20px
      weight: 600
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#3B82F6"
      - "#2563EB"
    background:
      - "#0B1220"
      - "#111A2E"
    text:
      - "#E5EAF3"
      - "#8B98B0"
    functional:
      - "#EF4444"
      - "#10B981"
todos:
  - id: backend-register-schema
    content: 在 schemas/auth.py 新增 RegisterRequest（username/password/display_name 字段约束）
    status: completed
  - id: backend-register-endpoint
    content: 在 api/auth.py 新增 POST /auth/register：查重 409、密码强度 400、建 user 返回 201 UserOut；可选加 registration_enabled 开关
    status: completed
    dependencies:
      - backend-register-schema
  - id: frontend-register-page
    content: 新建 pages/RegisterPage.tsx：复用登录页布局，含确认密码与本地校验，成功跳登录页
    status: completed
  - id: frontend-route-and-login
    content: App.tsx 加 /register 公开路由；LoginPage 加去注册链接与注册成功绿色提示
    status: completed
    dependencies:
      - frontend-register-page
  - id: verify-e2e
    content: 端到端验证：注册→登录、重名 409、弱密码 400、后台可见新用户
    status: completed
    dependencies:
      - backend-register-endpoint
      - frontend-route-and-login
---

## 需求概述

为企业内部知识库系统（web-agent）增加「用户自助注册」功能，输出一份具体的前后端手动实施清单，由用户自己写代码完成。

## 已确认策略

- **开放注册**：任何人打开注册页即可注册，注册后直接可用，role 固定为 `user`；无需审批、无需邀请码、User 表不加字段、不需要 alembic 迁移。
- **注册后跳回登录页**：提示「注册成功，请登录」，用户手动再登录；注册接口不返回 token、不写 Cookie。

## 核心功能

### 后端（2 个文件改动）

1. `app/schemas/auth.py` 新增 `RegisterRequest`：username（1-64）、password（1-128）、display_name（可选，≤64）。
2. `app/api/auth.py` 新增 `POST /auth/register`：

- 用户名查重 → 冲突返回 `USERNAME_TAKEN` 409（照抄 admin.py create_user 模式）
- 密码强度端点内校验（沿用 change_password 的 AppError 模式）：<8 位 → `WEAK_PASSWORD` 400；UTF-8 超 72 字节（bcrypt 硬限制）→ `PASSWORD_TOO_LONG` 400
- 创建 User（role 固定 "user"），201 返回 `UserOut`，不发 token、不写 Cookie
- 可选：`config.py` 加 `registration_enabled` 开关，关闭时 403

### 前端（3 处改动）

1. 新建 `pages/RegisterPage.tsx`：复用 LoginPage 左右分栏视觉与 Button/Input 组件，字段含用户名、显示名（可选）、密码、确认密码；前端先校验两次密码一致与最小长度再提交；成功后 `navigate("/login", { state: { registered: true } })`。
2. `App.tsx` 增加 `/register` 公开路由（不包 RequireAuth）。
3. `LoginPage.tsx`：表单下加「没有账号？去注册」链接；读取 location.state.registered 显示绿色「注册成功，请登录」提示。

### 验证

注册新用户 → 跳登录页 → 新账号登录成功；重复用户名提示已存在；短密码提示至少 8 位；管理后台用户列表可见新用户。

## 技术栈

- 后端：FastAPI + SQLAlchemy async + pydantic + bcrypt（复用现有 `hash_password`）
- 前端：React + TypeScript + react-router + zod + Tailwind + 自建 ui 组件（Button/Input）
- 无数据库变更、无新依赖

## 实施方案

### 后端

1. **`backend/app/schemas/auth.py` [MODIFY]** — 新增 `RegisterRequest`：

- `username: str = Field(min_length=1, max_length=64)`
- `password: str = Field(min_length=1, max_length=128)`
- `display_name: str = Field(default="", max_length=64)`
- 密码强度不放 Field（沿用 change_password 注释的理由：422 错误形状不利于前端透出友好文案，强度校验放端点内用 AppError）。

2. **`backend/app/api/auth.py` [MODIFY]** — 新增端点，模式照抄 `admin.py` 的 `create_user`（113-136 行）：

```python
@router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserOut:
```

- 查重：`select(User).where(User.username == body.username)` → 已存在抛 `AppError("USERNAME_TAKEN", "用户名已存在", 409)`
- 强度：`len(body.password) < 8` → `AppError("WEAK_PASSWORD", "密码至少 8 位", 400)`；`len(body.password.encode("utf-8")) > 72` → `AppError("PASSWORD_TOO_LONG", ..., 400)`
- 建用户：`User(username=..., password_hash=hash_password(...), display_name=..., role="user")`，`db.add` → `flush` → `commit`，返回 `UserOut.model_validate(user)`
- 不调用 `create_access_token`、不 `set_cookie`（跳回登录页策略）

3. **可选 `backend/app/config.py` [MODIFY]** — `registration_enabled: bool = True`；端点开头关闭时抛 `AppError("REGISTRATION_DISABLED", "注册已关闭", 403)`。

- `main.py` 无需改（auth router 已挂载）；无迁移。

### 前端

1. **`frontend/src/pages/RegisterPage.tsx` [NEW]**

- 复制 LoginPage 的整体结构（左右分栏、品牌区、卡片表单、shake 动画、密码可见切换），标题改为「注册」，副标题「创建内部账号」
- 字段：用户名（required）、显示名（可选）、密码、确认密码；`autoComplete` 用 `new-password`
- 提交前本地校验：两次密码一致（不一致就地红字提示不发请求）、密码 ≥8 位
- 调 `post("/auth/register", {...}, UserSchema)`（直接 import `../api/client` 的 `post`，**不改 AuthContext**）
- 成功：`navigate("/login", { state: { registered: true } })`；失败：错误块透出后端 message（如「用户名已存在」）；表单下加「已有账号？去登录」Link

2. **`frontend/src/App.tsx` [MODIFY]** — `/login` 路由旁加 `<Route path="/register" element={<RegisterPage />} />`（公开，不包 RequireAuth）。
3. **`frontend/src/pages/LoginPage.tsx` [MODIFY]**

- `useLocation()` 读 `state.registered`，在表单上方渲染绿色提示块「注册成功，请登录」（样式仿现有红色错误块，换 emerald 色）
- 登录按钮下加一行：`<Link to="/register">没有账号？去注册</Link>`

### 验证步骤

启动 uvicorn + vite → 开 `/register` 注册 → 跳登录页见绿色提示 → 新账号登录进首页；重复用户名 → 409「用户名已存在」；6 位密码 → 400「至少 8 位」；`/admin` 用户列表可见新用户（role=user）。

## 实施注意事项

- 统一错误形状：所有业务错误用 `AppError(code, 中文message, status)`，前端 `err.message` 直接透出，不要靠 422。
- bcrypt 72 字节硬限制必须前置校验，否则超长密码会 500。
- 用户名建议 `.strip()` 后查重与入库，避免首尾空格产生「幽灵重名」。
- 注册接口是公开端点，注意不要在日志打印密码明文。

## 设计风格

注册页完全沿用现有 LoginPage 的深色企业级视觉：左半品牌区（深墨底 + 网格纹理 + 品牌光晕，lg 屏显示），右半表单卡片（精细边框 + 渐入动效 + shake 错误动画）。表单在登录页基础上增加「显示名（可选）」与「确认密码」两个字段，保持 Input/Button 组件与错误提示块样式一致；成功反馈用 emerald 绿色提示块呈现在登录页。整体无新增设计语言，保证与现有 UI 零违和。