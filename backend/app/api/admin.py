"""管理后台：用户 CRUD 与用量 / 成本看板。全部端点要求 admin（require_admin）。"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AppError, not_found
from app.core.pagination import (
    LIKE_ESCAPE,
    PageParams,
    like_pattern,
    make_page,
    normalize_q,
    paginate,
)
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
from app.schemas.common import Page
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


@router.get("/admin/users", response_model=Page[AdminUserOut])
async def list_users(
    q: str | None = None,
    role: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[AdminUserOut]:
    """用户列表：q 匹配用户名/显示名，role 精确过滤，服务端分页。

    分页后 quotas 只查当页 user_id 集合（原先拉全量 quotas，分页后会白白多查）。
    """
    default_limit = get_settings().quota_monthly_tokens
    period = current_period()
    stmt = select(User)
    term = normalize_q(q)
    if term is not None:
        pattern = like_pattern(term)
        stmt = stmt.where(
            or_(
                User.username.ilike(pattern, escape=LIKE_ESCAPE),
                User.display_name.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if role is not None:
        stmt = stmt.where(User.role == role)
    stmt = stmt.order_by(User.created_at.asc(), User.id.asc())
    rows, total = await paginate(db, stmt, params)
    page_users = [row[0] for row in rows]
    quotas = (
        await db.execute(
            select(Quota).where(
                Quota.period == period, Quota.user_id.in_([u.id for u in page_users])
            )
        )
    ).scalars().all() if page_users else []
    by_user = {quota.user_id: quota for quota in quotas}
    return make_page(
        [
            AdminUserOut(
                id=u.id,
                username=u.username,
                display_name=u.display_name,
                role=u.role,
                created_at=u.created_at,
                month=_month_of(by_user.get(u.id), default_limit),
            )
            for u in page_users
        ],
        total,
        params,
    )


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


@router.get("/admin/usage/by-user", response_model=Page[UserUsage])
async def usage_by_user(
    q: str | None = None,
    days: int = Query(30, ge=1, le=365),
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[UserUsage]:
    """按用户用量：q 匹配用户名，cost 降序分页（days 时间窗与分页正交）。"""
    stmt = (
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
    )
    term = normalize_q(q)
    if term is not None:
        # username 是分组列：分组前过滤（写 where 而非 having）
        stmt = stmt.where(User.username.ilike(like_pattern(term), escape=LIKE_ESCAPE))
    stmt = stmt.order_by(
        func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).desc(), UsageRecord.user_id.asc()
    )
    rows, total = await paginate(db, stmt, params)
    return make_page(
        [
            UserUsage(
                user_id=r.uid, username=r.username, calls=r.calls,
                total_tokens=r.tokens, cost_cny=round(r.cost, 6),
            )
            for r in rows
        ],
        total,
        params,
    )


@router.get("/admin/usage/by-model", response_model=Page[ModelUsage])
async def usage_by_model(
    q: str | None = None,
    days: int = Query(30, ge=1, le=365),
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[ModelUsage]:
    """按模型用量：q 匹配模型名，cost 降序分页。"""
    stmt = (
        select(
            UsageRecord.model.label("model"),
            func.count().label("calls"),
            func.coalesce(func.sum(UsageRecord.prompt_tokens + UsageRecord.completion_tokens), 0).label("tokens"),
            func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).label("cost"),
        )
        .where(UsageRecord.created_at >= _since(days))
        .group_by(UsageRecord.model)
    )
    term = normalize_q(q)
    if term is not None:
        stmt = stmt.where(UsageRecord.model.ilike(like_pattern(term), escape=LIKE_ESCAPE))
    stmt = stmt.order_by(
        func.coalesce(func.sum(UsageRecord.cost_cny), 0.0).desc(), UsageRecord.model.asc()
    )
    rows, total = await paginate(db, stmt, params)
    return make_page(
        [
            ModelUsage(model=r.model, calls=r.calls, total_tokens=r.tokens, cost_cny=round(r.cost, 6))
            for r in rows
        ],
        total,
        params,
    )
