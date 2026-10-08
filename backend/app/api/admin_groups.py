"""用户组管理：组 CRUD 与成员维护。

创建/全量管理需 admin:group_manage 权限点；组 owner（创建者）可维护自己组的
基本信息与成员（无需管理权限点，便于文档共享场景自助维护）。
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.core.pagination import LIKE_ESCAPE, like_pattern, normalize_q
from app.core.security import get_current_user, require_permission
from app.db import get_db
from app.models.group import Group, GroupMember
from app.models.user import User
from app.schemas.rbac import (
    GroupCreate,
    GroupMemberAdd,
    GroupMemberOut,
    GroupOut,
    GroupUpdate,
    PrincipalSearchOut,
)
from app.services.authorization import get_user_permissions

router = APIRouter()

_group_manage = Depends(require_permission("admin:group_manage"))


async def _can_manage_group(db: AsyncSession, user: User, group: Group) -> bool:
    if group.owner_id == user.id:
        return True
    return "admin:group_manage" in await get_user_permissions(db, user.id)


async def _get_group(db: AsyncSession, group_id: uuid.UUID) -> Group:
    group = (await db.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
    if group is None:
        raise not_found("用户组")
    return group


async def _group_out(db: AsyncSession, group: Group) -> GroupOut:
    member_count = (
        await db.execute(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group.id))
    ).scalar_one()
    owner_name: str | None = None
    if group.owner_id is not None:
        owner_name = (
            await db.execute(select(User.display_name).where(User.id == group.owner_id))
        ).scalar_one_or_none()
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        owner_id=group.owner_id,
        owner_name=owner_name or None,
        member_count=member_count,
        created_at=group.created_at,
    )


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GroupOut]:
    """组列表：管理员（admin:group_manage）看全部，普通用户看自己 owner 或所在的组。"""
    perms = await get_user_permissions(db, user.id)
    stmt = select(Group)
    if "admin:group_manage" not in perms:
        my_groups = select(GroupMember.group_id).where(GroupMember.user_id == user.id)
        stmt = stmt.where(or_(Group.owner_id == user.id, Group.id.in_(my_groups)))
    term = normalize_q(q)
    if term is not None:
        stmt = stmt.where(Group.name.ilike(like_pattern(term), escape=LIKE_ESCAPE))
    stmt = stmt.order_by(Group.name.asc())
    groups = (await db.execute(stmt)).scalars().all()
    return [await _group_out(db, g) for g in groups]


@router.post("/groups", response_model=GroupOut, status_code=201, dependencies=[_group_manage])
async def create_group(
    body: GroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GroupOut:
    name = body.name.strip()
    if not name:
        raise AppError("BAD_GROUP", "组名不能为空", 400)
    exists = (await db.execute(select(Group).where(Group.name == name))).scalar_one_or_none()
    if exists is not None:
        raise AppError("GROUP_TAKEN", "组名已存在", 409)
    group = Group(name=name, description=body.description.strip(), owner_id=user.id)
    db.add(group)
    await db.flush()
    db.add(GroupMember(group_id=group.id, user_id=user.id))
    await db.commit()
    return await _group_out(db, group)


@router.patch("/groups/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GroupOut:
    group = await _get_group(db, group_id)
    if not await _can_manage_group(db, user, group):
        raise not_found("用户组")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise AppError("BAD_GROUP", "组名不能为空", 400)
        dup = (
            await db.execute(select(Group).where(Group.name == name, Group.id != group.id))
        ).scalar_one_or_none()
        if dup is not None:
            raise AppError("GROUP_TAKEN", "组名已存在", 409)
        group.name = name
    if body.description is not None:
        group.description = body.description.strip()
    await db.commit()
    return await _group_out(db, group)


@router.delete("/groups/{group_id}", status_code=204)
async def delete_group(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    group = await _get_group(db, group_id)
    if not await _can_manage_group(db, user, group):
        raise not_found("用户组")
    # group_members 依赖 FK CASCADE；document_grants 中的组授权由应用层清理
    from app.models.document_grant import DocumentGrant

    await db.execute(
        delete(DocumentGrant).where(
            DocumentGrant.grantee_type == "group", DocumentGrant.grantee_id == group.id
        )
    )
    await db.delete(group)
    await db.commit()


@router.get("/groups/{group_id}/members", response_model=list[GroupMemberOut])
async def list_members(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GroupMemberOut]:
    group = await _get_group(db, group_id)
    # 组成员/owner/管理员可查看成员
    is_member = (
        await db.execute(
            select(GroupMember.user_id).where(
                GroupMember.group_id == group.id, GroupMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if is_member is None and not await _can_manage_group(db, user, group):
        raise not_found("用户组")
    rows = (
        await db.execute(
            select(User.id, User.username, User.display_name)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group.id)
            .order_by(User.username.asc())
        )
    ).all()
    return [GroupMemberOut(user_id=r[0], username=r[1], display_name=r[2]) for r in rows]


@router.post("/groups/{group_id}/members", response_model=list[GroupMemberOut])
async def add_member(
    group_id: uuid.UUID,
    body: GroupMemberAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GroupMemberOut]:
    group = await _get_group(db, group_id)
    if not await _can_manage_group(db, user, group):
        raise not_found("用户组")
    target = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if target is None:
        raise not_found("用户")
    exists = (
        await db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id, GroupMember.user_id == body.user_id
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(GroupMember(group_id=group.id, user_id=body.user_id))
        await db.commit()
    return await list_members(group_id, db, user)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
async def remove_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    group = await _get_group(db, group_id)
    if not await _can_manage_group(db, user, group):
        raise not_found("用户组")
    member = (
        await db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id, GroupMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise not_found("组成员")
    await db.delete(member)
    await db.commit()


@router.get("/directory/principals", response_model=PrincipalSearchOut)
async def search_principals(
    q: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PrincipalSearchOut:
    """共享弹窗/成员添加的主体搜索：返回匹配的用户与组（各最多 8 条，任何登录用户可用）。"""
    term = normalize_q(q)
    users_stmt = select(User).order_by(User.username.asc()).limit(8)
    groups_stmt = select(Group).order_by(Group.name.asc()).limit(8)
    if term is not None:
        pattern = like_pattern(term)
        users_stmt = users_stmt.where(
            or_(
                User.username.ilike(pattern, escape=LIKE_ESCAPE),
                User.display_name.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
        groups_stmt = groups_stmt.where(Group.name.ilike(pattern, escape=LIKE_ESCAPE))
    users = (await db.execute(users_stmt)).scalars().all()
    groups = (await db.execute(groups_stmt)).scalars().all()
    return PrincipalSearchOut(
        users=[{"id": u.id, "username": u.username, "display_name": u.display_name} for u in users],
        groups=[{"id": g.id, "name": g.name} for g in groups],
    )
