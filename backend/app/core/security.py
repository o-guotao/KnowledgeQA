"""JWT 鉴权与口令散列。"""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError
from app.db import get_db
from app.models.user import User

ALGORITHM = "HS256"
bearer = HTTPBearer(auto_error=False)
# HttpOnly Cookie 名：浏览器自动携带，JS 不可读，避免 localStorage 被 XSS 窃取
AUTH_COOKIE_NAME = "web_agent_token"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    # 优先 Bearer 头（脚本/跨域部署兼容），否则回退 HttpOnly Cookie（浏览器前端）
    token = credentials.credentials if credentials is not None else request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise AppError("UNAUTHORIZED", "缺少登录凭证", 401)
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AppError("UNAUTHORIZED", "凭证无效或已过期", 401) from None
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise AppError("UNAUTHORIZED", "用户不存在", 401)
    return user


async def require_admin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """管理后台端点鉴权（兼容入口）：旧 role=admin 列或持 admin:user_manage 权限点放行。

    新端点应使用 require_permission("...") 做细粒度控制。
    """
    if user.role == "admin":
        return user
    from app.services.authorization import get_user_permissions

    if "admin:user_manage" in await get_user_permissions(db, user.id):
        return user
    raise AppError("FORBIDDEN", "需要管理员权限", 403)


def require_permission(code: str):
    """细粒度权限点校验依赖工厂：用户（经角色聚合）持有指定权限点才放行，否则 403。"""

    async def dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from app.services.authorization import get_user_permissions

        if code not in await get_user_permissions(db, user.id):
            raise AppError("FORBIDDEN", f"缺少权限：{code}", 403)
        return user

    return dependency


def require_any_permission(*codes: str):
    """持有任一指定权限点即放行（如只读角色列表对 user_manage / role_manage 同时开放）。"""

    async def dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from app.services.authorization import get_user_permissions

        perms = await get_user_permissions(db, user.id)
        if not any(code in perms for code in codes):
            raise AppError("FORBIDDEN", f"缺少权限：{' 或 '.join(codes)}", 403)
        return user

    return dependency
