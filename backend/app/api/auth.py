import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    AUTH_COOKIE_NAME,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, PasswordChange, RegisterRequest, TokenResponse, UserOut

router = APIRouter()

# 进程内滑动窗口限流（单实例部署按 IP 计数；多实例部署需换 Redis 等共享存储）。
# 防脚本批量注册刷库、用户名枚举与口令爆破。
_RATE_LIMITS = {
    "login": (20, 60),  # 每分钟每 IP 20 次
    "register": (10, 60),  # 每分钟每 IP 10 次
}
_rate_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(request: Request, bucket: str) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{ip}"
    max_hits, window = _RATE_LIMITS[bucket]
    now = time.monotonic()
    hits = _rate_hits[key]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= max_hits:
        raise AppError("RATE_LIMITED", "请求过于频繁，请稍后再试", 429)
    hits.append(now)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    _rate_limit(request, "login")
    # 用户名归一化（与注册一致）：大小写归一，避免 Demo/demo 两个账号
    user = (
        await db.execute(select(User).where(User.username == body.username.strip().lower()))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError("BAD_CREDENTIALS", "用户名或密码错误", 401)
    settings = get_settings()
    token = create_access_token(user.id)
    # HttpOnly Cookie：JS 不可读，防 XSS 窃取；SameSite=Lax 防跨站携带（CSRF）；
    # 生产环境强制 Secure（仅 HTTPS）。响应体仍返回 token，供脚本/跨域 Bearer 场景使用。
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/auth/logout", status_code=204)
async def logout(response: Response) -> None:
    # HttpOnly Cookie 只能由服务端清除
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/auth/change-password", status_code=204)
async def change_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """修改当前用户密码：先校验当前密码，再做强度校验。

    强度校验放端点内（而非 Field）：FastAPI 422 的 detail 是列表形状，前端只能透成
    通用文案；AppError 走统一错误形状可透出具体原因。

    注：JWT 无状态、本系统无令牌吊销机制，改密后既有会话在过期前仍有效。
    """
    if not verify_password(body.current_password, user.password_hash):
        raise AppError("BAD_CREDENTIALS", "当前密码不正确", 401)
    if len(body.new_password) < 8:
        raise AppError("WEAK_PASSWORD", "新密码至少 8 位", 400)
    if len(body.new_password.encode("utf-8")) > 72:
        # bcrypt 硬限制：超过 72 字节会 raise ValueError（避免 500）
        raise AppError("PASSWORD_TOO_LONG", "新密码过长（按 UTF-8 计不超过 72 字节）", 400)
    if body.new_password == body.current_password:
        raise AppError("SAME_PASSWORD", "新密码不能与当前密码相同", 400)
    user.password_hash = hash_password(body.new_password)
    await db.commit()


@router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)) -> UserOut:
    """开放注册：role 固定 user；不发 token、不写 Cookie，前端注册成功后跳回登录页。

    密码强度校验放端点内（同 change_password）：AppError 统一错误形状便于前端透出文案。
    """
    _rate_limit(request, "register")
    setting = get_settings()
    if not setting.registration_enabled:
        raise AppError("REGISTRATION_DISABLED", "注册已关闭", 403)
    # 用户名归一化：去首尾空白 + 小写（登录查询同样归一，大小写不产生两个账号）
    username = body.username.strip().lower()
    if not username:
        raise AppError("BAD_USERNAME", "用户名不能为空", 400)
    exists = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if exists is not None:
        raise AppError("USERNAME_TAKEN", "用户名已存在", 409)
    if len(body.password) < 8:
        raise AppError("WEAK_PASSWORD", "密码至少 8 位", 400)
    if len(body.password.encode("utf-8")) > 72:
        # bcrypt 硬限制：超过 72 字节会 raise ValueError（避免 500）
        raise AppError("PASSWORD_TOO_LONG", "密码过长（按 UTF-8 计不超过 72 字节）", 400)
    user = User(
        username=username,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
        role="user",
    )

    db.add(user)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        # 并发注册兜底：username 唯一索引拦下，翻译为用户可读 409（与上传判重同模式）
        await db.rollback()
        raise AppError("USERNAME_TAKEN", "用户名已存在", 409)
    return UserOut.model_validate(user)
