"""管理后台：用户 CRUD、角色权限管理（RBAC）与用量 / 成本看板。

细粒度权限点：用户相关 admin:user_manage；角色相关 admin:role_manage。
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select
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
from app.core.permissions import PERMISSION_CATALOG
from app.core.security import get_current_user, hash_password, require_any_permission, require_permission
from app.db import get_db
from app.models.quota import Quota
from app.models.rbac import Permission, Role, RolePermission, UserRole
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
from app.schemas.rbac import PermissionOut, RoleCreate, RoleOut, RoleUpdate, UserRolesUpdate
from app.services.authorization import get_user_role_names, invalidate_permissions
from app.services.cost import current_period

router = APIRouter()

VALID_ROLES = ("user", "admin")  # 旧 role 列取值（兼容字段，真实权限以 user_roles 为准）

_user_manage = Depends(require_permission("admin:user_manage"))
_role_manage = Depends(require_permission("admin:role_manage"))


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
    """持有内置 admin 角色的用户数（"最后一名 admin"保护口径）。"""
    return (
        await db.execute(
            select(func.count(func.distinct(UserRole.user_id)))
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == "admin")
        )
    ).scalar_one()


async def _role_names_by_user(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_(user_ids))
        )
    ).all()
    result: dict[uuid.UUID, list[str]] = {}
    for uid, name in rows:
        result.setdefault(uid, []).append(name)
    return result


async def _sync_legacy_role(db: AsyncSession, user: User) -> None:
    """回写旧 users.role 兼容列：持 admin 角色则为 admin，否则 user。"""
    names = await get_user_role_names(db, user.id)
    user.role = "admin" if "admin" in names else "user"


async def _set_user_roles(db: AsyncSession, user: User, role_ids: list[uuid.UUID]) -> None:
    """整体替换用户角色（含最后一名 admin 保护与旧列回写）。"""
    roles = (
        (await db.execute(select(Role).where(Role.id.in_(role_ids)))).scalars().all()
        if role_ids
        else []
    )
    if len(roles) != len(set(role_ids)):
        raise AppError("BAD_ROLE", "存在无效的角色 id", 400)
    removing_admin = (
        "admin" in await get_user_role_names(db, user.id)
        and not any(r.name == "admin" for r in roles)
    )
    if removing_admin and await _admin_count(db) <= 1:
        raise AppError("LAST_ADMIN", "至少保留一个管理员", 400)
    await db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.flush()
    await _sync_legacy_role(db, user)
    invalidate_permissions(user.id)


# ---------- 用户 CRUD ----------


@router.get("/admin/users", response_model=Page[AdminUserOut], dependencies=[_user_manage])
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
    roles_by_user = await _role_names_by_user(db, [u.id for u in page_users])
    return make_page(
        [
            AdminUserOut(
                id=u.id,
                username=u.username,
                display_name=u.display_name,
                role=u.role,
                created_at=u.created_at,
                month=_month_of(by_user.get(u.id), default_limit),
                roles=roles_by_user.get(u.id, []),
            )
            for u in page_users
        ],
        total,
        params,
    )


@router.post("/admin/users", response_model=AdminUserOut, status_code=201, dependencies=[_user_manage])
async def create_user(body: AdminUserCreate, db: AsyncSession = Depends(get_db)) -> AdminUserOut:
    if body.role not in VALID_ROLES:
        raise AppError("BAD_ROLE", "role 必须是 user 或 admin", 400)
    # 用户名归一化（与注册/登录一致）：去首尾空白 + 小写
    username = body.username.strip().lower()
    if not username:
        raise AppError("BAD_USERNAME", "用户名不能为空", 400)
    exists = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if exists is not None:
        raise AppError("USERNAME_TAKEN", "用户名已存在", 409)
    user = User(
        username=username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()
    # 分配同名内置角色（user/admin）
    role = (await db.execute(select(Role).where(Role.name == body.role))).scalar_one_or_none()
    if role is not None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.commit()
    return AdminUserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        created_at=user.created_at,
        month=_month_of(None, get_settings().quota_monthly_tokens),
        roles=[body.role],
    )


@router.patch("/admin/users/{user_id}", response_model=AdminUserOut, dependencies=[_user_manage])
async def update_user(user_id: uuid.UUID, body: AdminUserPatch, db: AsyncSession = Depends(get_db)) -> AdminUserOut:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("用户")
    if body.role is not None:
        # 旧兼容字段：整体替换为同名内置角色
        if body.role not in VALID_ROLES:
            raise AppError("BAD_ROLE", "role 必须是 user 或 admin", 400)
        target = (await db.execute(select(Role).where(Role.name == body.role))).scalar_one_or_none()
        if target is None:
            raise AppError("BAD_ROLE", "内置角色不存在，请先执行权限目录同步", 400)
        await _set_user_roles(db, user, [target.id])
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
        roles=await get_user_role_names(db, user.id),
    )


@router.delete("/admin/users/{user_id}", status_code=204, dependencies=[_user_manage])
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
    if "admin" in await get_user_role_names(db, user.id) and await _admin_count(db) <= 1:
        raise AppError("LAST_ADMIN", "至少保留一个管理员", 400)
    # postgres 依赖 FK ondelete CASCADE 清理关联；sqlite 未强制 FK，靠应用层按 user_id 隔离查询，孤儿不可见。
    await db.delete(user)
    await db.commit()
    invalidate_permissions(user_id)


# ---------- 用量 / 成本看板 ----------


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/admin/usage/daily", response_model=list[DailyUsage], dependencies=[_user_manage])
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


@router.get("/admin/usage/by-user", response_model=Page[UserUsage], dependencies=[_user_manage])
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


@router.get("/admin/usage/by-model", response_model=Page[ModelUsage], dependencies=[_user_manage])
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


# ---------- 角色权限管理（RBAC） ----------


async def _role_out(db: AsyncSession, role: Role) -> RoleOut:
    codes = (
        await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        )
    ).scalars().all()
    member_count = (
        await db.execute(select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id))
    ).scalar_one()
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        is_builtin=role.is_builtin,
        permissions=sorted(codes),
        member_count=member_count,
    )


def _validate_permission_codes(codes: list[str]) -> list[str]:
    invalid = set(codes) - set(PERMISSION_CATALOG)
    if invalid:
        raise AppError("BAD_PERMISSION", f"未知权限点：{', '.join(sorted(invalid))}", 400)
    return sorted(set(codes))


@router.get("/admin/permissions", response_model=list[PermissionOut], dependencies=[_role_manage])
async def list_permissions(db: AsyncSession = Depends(get_db)) -> list[PermissionOut]:
    """权限点目录（代码常量 upsert 入表，此处读库保证与表一致）。"""
    rows = (await db.execute(select(Permission).order_by(Permission.code))).scalars().all()
    return [PermissionOut(code=p.code, description=p.description) for p in rows]


@router.get(
    "/admin/roles",
    response_model=list[RoleOut],
    dependencies=[Depends(require_any_permission("admin:role_manage", "admin:user_manage"))],
)
async def list_roles(db: AsyncSession = Depends(get_db)) -> list[RoleOut]:
    roles = (await db.execute(select(Role).order_by(Role.is_builtin.desc(), Role.name))).scalars().all()
    return [await _role_out(db, r) for r in roles]


@router.post("/admin/roles", response_model=RoleOut, status_code=201, dependencies=[_role_manage])
async def create_role(body: RoleCreate, db: AsyncSession = Depends(get_db)) -> RoleOut:
    name = body.name.strip()
    if not name:
        raise AppError("BAD_ROLE", "角色名不能为空", 400)
    exists = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if exists is not None:
        raise AppError("ROLE_TAKEN", "角色名已存在", 409)
    codes = _validate_permission_codes(body.permissions)
    role = Role(name=name, description=body.description.strip(), is_builtin=False)
    db.add(role)
    await db.flush()
    perm_rows = (
        (await db.execute(select(Permission).where(Permission.code.in_(codes)))).scalars().all()
        if codes
        else []
    )
    for perm in perm_rows:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db.commit()
    invalidate_permissions()
    return await _role_out(db, role)


@router.patch("/admin/roles/{role_id}", response_model=RoleOut, dependencies=[_role_manage])
async def update_role(role_id: uuid.UUID, body: RoleUpdate, db: AsyncSession = Depends(get_db)) -> RoleOut:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise not_found("角色")
    if body.description is not None:
        role.description = body.description.strip()
    if body.permissions is not None:
        if role.name == "admin":
            # 防锁死：内置 admin 角色始终持有全部权限点，不可裁剪
            raise AppError("ADMIN_ROLE_LOCKED", "内置 admin 角色的权限不可修改", 400)
        codes = _validate_permission_codes(body.permissions)
        perm_rows = (
            (await db.execute(select(Permission).where(Permission.code.in_(codes)))).scalars().all()
            if codes
            else []
        )
        await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for perm in perm_rows:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db.commit()
    invalidate_permissions()
    return await _role_out(db, role)


@router.delete("/admin/roles/{role_id}", status_code=204, dependencies=[_role_manage])
async def delete_role(role_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise not_found("角色")
    if role.is_builtin:
        raise AppError("BUILTIN_ROLE", "内置角色不可删除", 400)
    # role_permissions / user_roles 依赖 FK CASCADE 一并清理
    await db.delete(role)
    await db.commit()
    invalidate_permissions()


@router.get("/admin/users/{user_id}/roles", response_model=list[RoleOut], dependencies=[_user_manage])
async def get_user_roles(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[RoleOut]:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("用户")
    roles = (
        await db.execute(
            select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        )
    ).scalars().all()
    return [await _role_out(db, r) for r in roles]


@router.put("/admin/users/{user_id}/roles", response_model=list[RoleOut], dependencies=[_user_manage])
async def put_user_roles(
    user_id: uuid.UUID, body: UserRolesUpdate, db: AsyncSession = Depends(get_db)
) -> list[RoleOut]:
    """整体替换用户角色（含最后一名 admin 保护与旧 role 列回写）。"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise not_found("用户")
    await _set_user_roles(db, user, body.role_ids)
    await db.commit()
    roles = (
        await db.execute(
            select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        )
    ).scalars().all()
    return [await _role_out(db, r) for r in roles]
