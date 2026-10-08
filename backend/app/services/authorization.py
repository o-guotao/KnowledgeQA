"""统一授权服务：RBAC 权限点聚合（带进程内缓存）+ 文档级 ACL 判定 + 可见性 SQL 条件。

判定规则（文档）：
- read：owner | document:read_all 权限点 | 显式授权（个人直授或经用户组继承，write 蕴含 read）
        | visibility == 'team'
- write：owner | 显式 write 授权 | document:team_manage 权限点且 visibility == 'team'
- share：owner | document:share 权限点且可写

越权统一返回 404 由路由层负责，本模块只产出布尔判定与 SQL 过滤条件。
"""
import time
import uuid

from sqlalchemy import ColumnElement, and_, delete, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import BUILTIN_ROLES, LEGACY_ROLE_MAP, PERMISSION_CATALOG
from app.models.document import Document
from app.models.document_grant import DocumentGrant
from app.models.group import GroupMember
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.user import User

# ---- 权限点进程内缓存：角色/组成员写操作后主动失效，TTL 兜底 ----
_CACHE_TTL_SECONDS = 60.0
_perm_cache: dict[uuid.UUID, tuple[frozenset[str], float]] = {}


def invalidate_permissions(user_id: uuid.UUID | None = None) -> None:
    """失效权限缓存；user_id 为 None 时清空全部（角色/权限定义变更）。"""
    if user_id is None:
        _perm_cache.clear()
    else:
        _perm_cache.pop(user_id, None)


async def get_user_permissions(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """聚合用户权限点集合：user_roles -> role_permissions -> permissions.code。"""
    now = time.monotonic()
    hit = _perm_cache.get(user_id)
    if hit and now - hit[1] < _CACHE_TTL_SECONDS:
        return set(hit[0])
    stmt = (
        select(Permission.code)
        .select_from(UserRole)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserRole.user_id == user_id)
    )
    codes = frozenset((await db.execute(stmt)).scalars().all())
    _perm_cache[user_id] = (codes, now)
    return set(codes)


async def get_user_role_names(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    rows = (
        await db.execute(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
        )
    ).scalars().all()
    return list(rows)


# ---- 目录同步：启动时 upsert 权限点与内置角色（sqlite create_all 模式下无迁移，靠此初始化） ----
async def sync_rbac_catalog(db: AsyncSession) -> None:
    """将代码常量中的权限点目录与内置角色 upsert 入表，并为无角色用户回填默认角色。幂等。"""
    # 1. 权限点
    existing_perms = {p.code: p for p in (await db.execute(select(Permission))).scalars().all()}
    for code, desc in PERMISSION_CATALOG.items():
        perm = existing_perms.get(code)
        if perm is None:
            db.add(Permission(code=code, description=desc))
        elif perm.description != desc:
            perm.description = desc
    await db.flush()
    perm_by_code = {p.code: p for p in (await db.execute(select(Permission))).scalars().all()}

    # 2. 内置角色
    existing_roles = {r.name: r for r in (await db.execute(select(Role))).scalars().all()}
    for name, (desc, codes) in BUILTIN_ROLES.items():
        role = existing_roles.get(name)
        if role is None:
            role = Role(name=name, description=desc, is_builtin=True)
            db.add(role)
            await db.flush()
        else:
            role.description = desc
            role.is_builtin = True
        # 内置角色权限点只增不删（admin 角色保证始终持有全部权限点）
        have = set(
            (await db.execute(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            )).scalars().all()
        )
        for code in codes:
            if code not in have:
                db.add(RolePermission(role_id=role.id, permission_id=perm_by_code[code].id))

    # 3. 无角色用户按旧 users.role 列回填（迁移 0016 在 PG 已做，此处兜底 sqlite/新增历史数据）
    users = (await db.execute(select(User))).scalars().all()
    if users:
        assigned = set((await db.execute(select(UserRole.user_id))).scalars().all())
        role_by_name = {r.name: r for r in (await db.execute(select(Role))).scalars().all()}
        default_role = role_by_name["user"]
        for u in users:
            if u.id not in assigned:
                role = role_by_name.get(LEGACY_ROLE_MAP.get(u.role or "", "user"), default_role)
                db.add(UserRole(user_id=u.id, role_id=role.id))
    await db.commit()
    invalidate_permissions()


# ---- 文档 ACL 判定 ----
def _grant_condition(document_id_col: ColumnElement, user_id: uuid.UUID) -> ColumnElement:
    """EXISTS 子查询：文档对某用户存在显式授权（个人直授或经用户组成员继承）。"""
    group_ids = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    return (
        select(DocumentGrant.id)
        .where(
            DocumentGrant.document_id == document_id_col,
            or_(
                and_(DocumentGrant.grantee_type == "user", DocumentGrant.grantee_id == user_id),
                and_(DocumentGrant.grantee_type == "group", DocumentGrant.grantee_id.in_(group_ids)),
            ),
        )
        .exists()
    )


async def _document_grant_level(db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID) -> str | None:
    """返回用户对文档的显式授权级别：'write' | 'read' | None（个人直授 + 组继承取最高）。"""
    group_ids = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    stmt = select(DocumentGrant.permission).where(
        DocumentGrant.document_id == document_id,
        or_(
            and_(DocumentGrant.grantee_type == "user", DocumentGrant.grantee_id == user_id),
            and_(DocumentGrant.grantee_type == "group", DocumentGrant.grantee_id.in_(group_ids)),
        ),
    )
    levels = (await db.execute(stmt)).scalars().all()
    if "write" in levels:
        return "write"
    return "read" if levels else None


async def can_read_document(db: AsyncSession, user: User, doc: Document, perms: set[str] | None = None) -> bool:
    if doc.user_id == user.id:
        return True
    perms = perms if perms is not None else await get_user_permissions(db, user.id)
    if "document:read_all" in perms:
        return True
    if await _document_grant_level(db, user.id, doc.id) is not None:
        return True
    return doc.visibility == "team"


async def can_write_document(db: AsyncSession, user: User, doc: Document, perms: set[str] | None = None) -> bool:
    if doc.user_id == user.id:
        return True
    perms = perms if perms is not None else await get_user_permissions(db, user.id)
    if "document:team_manage" in perms and doc.visibility == "team":
        return True
    return await _document_grant_level(db, user.id, doc.id) == "write"


async def can_share_document(db: AsyncSession, user: User, doc: Document, perms: set[str] | None = None) -> bool:
    if doc.user_id == user.id:
        return True
    perms = perms if perms is not None else await get_user_permissions(db, user.id)
    return "document:share" in perms and await can_write_document(db, user, doc, perms)


def visible_document_condition(user_id: uuid.UUID, perms: set[str]) -> ColumnElement:
    """生成"用户可读文档"的可复用 SQL 过滤条件（基于 Document 列）。

    供文档列表与 RAG 召回（Chunk join Document 后）统一使用；持 read_all 权限时恒真。
    """
    if "document:read_all" in perms:
        return true()
    return or_(
        Document.user_id == user_id,
        Document.visibility == "team",
        _grant_condition(Document.id, user_id),
    )


# 原生 SQL 片段（rag.py 的 tsvector / LIKE 回退路径使用，d 为 documents 别名）；
# 与 visible_document_condition 语义保持一致，持 read_all 权限的用户在 Python 侧短路为 "TRUE"。
VISIBLE_DOCUMENT_RAW_SQL = """
(
  c.user_id = :uid OR d.visibility = 'team' OR EXISTS (
    SELECT 1 FROM document_grants g
    WHERE g.document_id = d.id AND (
      (g.grantee_type = 'user' AND g.grantee_id = :uid)
      OR (g.grantee_type = 'group' AND g.grantee_id IN (
        SELECT gm.group_id FROM group_members gm WHERE gm.user_id = :uid
      ))
    )
  )
)
"""


def visible_document_raw_sql(perms: set[str]) -> str:
    """原生 SQL 召回路径的可见性片段；read_all 权限短路为恒真。"""
    if "document:read_all" in perms:
        return "TRUE"
    return VISIBLE_DOCUMENT_RAW_SQL.strip()


async def upsert_document_grant(
    db: AsyncSession,
    document_id: uuid.UUID,
    grantee_type: str,
    grantee_id: uuid.UUID,
    permission: str,
    granted_by: uuid.UUID,
) -> DocumentGrant:
    """授予/升级权限：同一 (document, grantee) 仅一条记录，write 覆盖 read。"""
    stmt = select(DocumentGrant).where(
        DocumentGrant.document_id == document_id,
        DocumentGrant.grantee_type == grantee_type,
        DocumentGrant.grantee_id == grantee_id,
    )
    grant = (await db.execute(stmt)).scalar_one_or_none()
    if grant is None:
        grant = DocumentGrant(
            document_id=document_id,
            grantee_type=grantee_type,
            grantee_id=grantee_id,
            permission=permission,
            granted_by=granted_by,
        )
        db.add(grant)
    else:
        grant.permission = permission
        grant.granted_by = granted_by
    return grant


async def revoke_document_grant(
    db: AsyncSession, document_id: uuid.UUID, grantee_type: str, grantee_id: uuid.UUID
) -> bool:
    result = await db.execute(
        delete(DocumentGrant).where(
            DocumentGrant.document_id == document_id,
            DocumentGrant.grantee_type == grantee_type,
            DocumentGrant.grantee_id == grantee_id,
        )
    )
    return result.rowcount > 0
