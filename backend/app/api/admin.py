"""管理后台：用户 CRUD 与用量 / 成本看板。全部端点要求 admin（require_admin）。"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, not_found
from app.core.security import get_current_user, hash_password, require_admin
from app.db import get_db
from app.models.quota import Quota
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserMonth,
    AdminUserOut,
    AdminUserPatch,
    DailyUsage,
    ModelUsage,
    UserUsage,
)
from app.services.cost import current_period

router = APIRouter(dependencies=[Depends(require_admin)])

VALID_ROLES = ("user", "admin")


def _month_of(quota: Quota | None, default_limit: int) -> AdminUserMonth:
    p = quota.prompt_tokens if quota else 0
    c = quota.completion_tokens if quota else 0
    return AdminUserMonth(
        prompt_tokens=p,
        completion_tokens=c,
        total_tokens=p + c,
        cost_cny=quota.cost_cny if quota else 0.0,
        limit_tokens=(quota.limit_tokens if quota else 0) or default_limit,
    )


async def _admin_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(User).where(User.role == "admin"))).scalar_one()


# ---------- 用户 CRUD ----------


@router.get("/admin/users", response_model=list[AdminUserOut])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[AdminUserOut]:
    default_limit = get_settings().quota_monthly_tokens
    period = current_period()
    users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    quotas = (await db.execute(select(Quota).where(Quota.period == period))).scalars().all()
    by_user = {q.user_id: q for q in quotas}
    return [
        AdminUserOut(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            role=u.role,
            created_at=u.created_at,
            month=_month_of(by_user.get(u.id), default_limit),
        )
        for u in users
    ]


@router.post("/admin/users", response_model=AdminUserOut, status_code=201)
async def create_user(body: AdminUserCreate, db: AsyncSession = Depends(get_db)) -> AdminUserOut:
    if body.role not in VALID_ROLES:
        raise AppError("BAD_ROLE", "role 必须是 user 或 admin", 400)
    exists = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if exists is not None:
        raise AppError("USERNAME_TAKEN", "用户名已存在", 409)
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()
    await db.commit()
    return AdminUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        created_at=user.created_at,
        month=_month_of(None, get_settings().quota_monthly_tokens),
    )


@router.patch("/admin/users/{user_id}", response_model=AdminUserOut)
async def update_user(user_id: uuid.UUID, body: AdminUserPatch, db: AsyncSession = Depends(get_db)) -> AdminUserOut:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("用户")
    if body.role is not None:
        if body.role not in VALID_ROLES:
            raise AppError("BAD_ROLE", "role 必须是 user 或 admin", 400)
        if user.role == "admin" and body.role != "admin" and await _admin_count(db) <= 1:
            raise AppError("LAST_ADMIN", "至少保留一个管理员", 400)
        user.role = body.role
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.limit_tokens is not None:
        period = current_period()
        quota = (
            await db.execute(select(Quota).where(Quota.user_id == user.id, Quota.period == period))
        ).scalar_one_or_none()
        if quota is None:
            db.add(Quota(user_id=user.id, period=period, limit_tokens=body.limit_tokens))
        else:
            quota.limit_tokens = body.limit_tokens
    await db.commit()
    quota = (
        await db.execute(select(Quota).where(Quota.user_id == user.id, Quota.period == current_period()))
    ).scalar_one_or_none()
    return AdminUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        created_at=user.created_at,
        month=_month_of(quota, get_settings().quota_monthly_tokens),
    )


@router.delete("/admin/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    me: User = Depends(get_current_user),
) -> None:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("用户")
    if user.id == me.id:
        raise AppError("SELF_DELETE", "不能删除当前登录的管理员账号", 400)
    if user.role == "admin" and await _admin_count(db) <= 1:
        raise AppError("LAST_ADMIN", "至少保留一个管理员", 400)
    # postgres 依赖 FK ondelete CASCADE 清理关联；sqlite 未强制 FK，靠应用层按 user_id 隔离查询，孤儿不可见。
    await db.delete(user)
    await db.commit()


# ---------- 用量 / 成本看板 ----------


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/admin/usage/daily", response_model=list[DailyUsage])
async def usage_daily(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)) -> list[DailyUsage]:
    day = func.date(UsageRecord.created_at)
    rows = (
        await db.execute(
            select(
                day.label("d"),
                func.count().label("calls"),
                func.coalesce(func.sum(UsageRecord.prompt_tokens), 0).label("p"),
                func.coalesce(func.sum(UsageRecord.completion_tokens), 0).label("c"),
                func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).label("cost"),
            )
            .where(UsageRecord.created_at >= _since(days))
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return [
        DailyUsage(
            date=str(r.d),
            calls=r.calls,
            prompt_tokens=r.p,
            completion_tokens=r.c,
            total_tokens=r.p + r.c,
            cost_cny=round(r.cost, 6),
        )
        for r in rows
    ]


@router.get("/admin/usage/by-user", response_model=list[UserUsage])
async def usage_by_user(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)) -> list[UserUsage]:
    rows = (
        await db.execute(
            select(
                UsageRecord.user_id.label("uid"),
                User.username.label("username"),
                func.count().label("calls"),
                func.coalesce(func.sum(UsageRecord.prompt_tokens + UsageRecord.completion_tokens), 0).label("tokens"),
                func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).label("cost"),
            )
            .join(User, User.id == UsageRecord.user_id)
            .where(UsageRecord.created_at >= _since(days))
            .group_by(UsageRecord.user_id, User.username)
            .order_by(func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).desc())
        )
    ).all()
    return [
        UserUsage(user_id=r.uid, username=r.username, calls=r.calls, total_tokens=r.tokens, cost_cny=round(r.cost, 6))
        for r in rows
    ]


@router.get("/admin/usage/by-model", response_model=list[ModelUsage])
async def usage_by_model(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)) -> list[ModelUsage]:
    rows = (
        await db.execute(
            select(
                UsageRecord.model.label("model"),
                func.count().label("calls"),
                func.coalesce(func.sum(UsageRecord.prompt_tokens + UsageRecord.completion_tokens), 0).label("tokens"),
                func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).label("cost"),
            )
            .where(UsageRecord.created_at >= _since(days))
            .group_by(UsageRecord.model)
            .order_by(func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).desc())
        )
    ).all()
    return [
        ModelUsage(model=r.model, calls=r.calls, total_tokens=r.tokens, cost_cny=round(r.cost, 6))
        for r in rows
    ]
