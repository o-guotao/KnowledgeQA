from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
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
from app.schemas.auth import LoginRequest, PasswordChange, TokenResponse, UserOut

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = (
        await db.execute(select(User).where(User.username == body.username))
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
