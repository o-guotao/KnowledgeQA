"""授权服务（RBAC + 文档级 ACL）单元测试。

覆盖：权限点聚合、文档读/写/分享判定全路径（owner / 权限点 / 个人直授 /
用户组继承 / visibility 叠加）、grant upsert 与撤销、可见性 SQL 条件、
目录同步幂等与无角色用户回填。sqlite 内存库跑通即验证方言兼容路径。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 注册全部模型
from app.db import Base
from app.models.document import Document
from app.models.document_grant import DocumentGrant
from app.models.group import Group, GroupMember
from app.models.rbac import Role, UserRole
from app.models.user import User
from app.services import authorization as authz


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await authz.sync_rbac_catalog(session)
        yield session
    authz.invalidate_permissions()
    await engine.dispose()


async def make_user(db, username: str, role_name: str = "user") -> User:
    user = User(username=username, password_hash="x", role="admin" if role_name == "admin" else "user")
    db.add(user)
    await db.flush()
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.commit()
    authz.invalidate_permissions(user.id)
    return user


async def make_doc(db, owner: User, visibility: str = "private") -> Document:
    doc = Document(user_id=owner.id, filename=f"{uuid.uuid4().hex[:8]}.txt", visibility=visibility, object_key="k")
    db.add(doc)
    await db.commit()
    return doc


async def make_group(db, name: str, member_ids: list[uuid.UUID]) -> Group:
    group = Group(name=name)
    db.add(group)
    await db.flush()
    for uid in member_ids:
        db.add(GroupMember(group_id=group.id, user_id=uid))
    await db.commit()
    return group


# ---------- 权限点聚合与目录同步 ----------


@pytest.mark.asyncio
async def test_admin_role_has_all_permissions(db):
    from app.core.permissions import ALL_PERMISSIONS

    admin = await make_user(db, "a1", "admin")
    perms = await authz.get_user_permissions(db, admin.id)
    assert set(ALL_PERMISSIONS) <= perms


@pytest.mark.asyncio
async def test_user_role_has_base_permissions(db):
    user = await make_user(db, "u1", "user")
    perms = await authz.get_user_permissions(db, user.id)
    assert perms == {"document:create", "document:share"}


@pytest.mark.asyncio
async def test_sync_catalog_idempotent_and_backfill(db):
    # 无角色用户：sync 后回填旧 role 列对应的内置角色
    orphan = User(username="orphan", password_hash="x", role="admin")
    db.add(orphan)
    await db.commit()
    await authz.sync_rbac_catalog(db)
    roles = await authz.get_user_role_names(db, orphan.id)
    assert roles == ["admin"]
    # 再次执行幂等（不重复插入）
    await authz.sync_rbac_catalog(db)
    role_count = (await db.execute(select(func.count()).select_from(Role))).scalar_one()
    await authz.sync_rbac_catalog(db)
    assert (await db.execute(select(func.count()).select_from(Role))).scalar_one() == role_count


# ---------- 文档读判定 ----------


@pytest.mark.asyncio
async def test_read_paths(db):
    owner = await make_user(db, "owner")
    other = await make_user(db, "other")
    admin = await make_user(db, "adm", "admin")
    private_doc = await make_doc(db, owner, "private")
    team_doc = await make_doc(db, owner, "team")

    assert await authz.can_read_document(db, owner, private_doc)          # owner
    assert await authz.can_read_document(db, admin, private_doc)          # document:read_all
    assert not await authz.can_read_document(db, other, private_doc)      # 私有未授权
    assert await authz.can_read_document(db, other, team_doc)             # visibility=team

    # 个人直授 read
    await authz.upsert_document_grant(db, private_doc.id, "user", other.id, "read", owner.id)
    await db.commit()
    assert await authz.can_read_document(db, other, private_doc)


@pytest.mark.asyncio
async def test_read_via_group_grant(db):
    owner = await make_user(db, "owner2")
    member = await make_user(db, "member")
    outsider = await make_user(db, "outsider")
    doc = await make_doc(db, owner, "private")
    group = await make_group(db, "dept", [member.id])

    await authz.upsert_document_grant(db, doc.id, "group", group.id, "read", owner.id)
    await db.commit()
    assert await authz.can_read_document(db, member, doc)      # 组成员继承
    assert not await authz.can_read_document(db, outsider, doc)


# ---------- 文档写判定 ----------


@pytest.mark.asyncio
async def test_write_paths(db):
    owner = await make_user(db, "w-owner")
    reader = await make_user(db, "w-reader")
    writer = await make_user(db, "w-writer")
    admin = await make_user(db, "w-admin", "admin")
    doc = await make_doc(db, owner, "private")
    team_doc = await make_doc(db, owner, "team")

    assert await authz.can_write_document(db, owner, doc)
    assert not await authz.can_write_document(db, reader, doc)

    # read 授权不蕴含 write；write 蕴含 read
    await authz.upsert_document_grant(db, doc.id, "user", reader.id, "read", owner.id)
    await authz.upsert_document_grant(db, doc.id, "user", writer.id, "write", owner.id)
    await db.commit()
    assert not await authz.can_write_document(db, reader, doc)
    assert await authz.can_write_document(db, writer, doc)
    assert await authz.can_read_document(db, writer, doc)

    # team_manage（admin 角色持有）仅对 team 文档可写，他人私有文档不碰
    assert await authz.can_write_document(db, admin, team_doc)
    assert not await authz.can_write_document(db, admin, doc)


@pytest.mark.asyncio
async def test_grant_upsert_overrides_and_revoke(db):
    owner = await make_user(db, "g-owner")
    target = await make_user(db, "g-target")
    doc = await make_doc(db, owner, "private")

    await authz.upsert_document_grant(db, doc.id, "user", target.id, "read", owner.id)
    await authz.upsert_document_grant(db, doc.id, "user", target.id, "write", owner.id)
    await db.commit()
    # 同一 (document, grantee) 仅一条记录，write 覆盖 read
    grants = (
        await db.execute(select(DocumentGrant).where(DocumentGrant.document_id == doc.id))
    ).scalars().all()
    assert len(grants) == 1
    assert grants[0].permission == "write"
    assert await authz._document_grant_level(db, target.id, doc.id) == "write"

    assert await authz.revoke_document_grant(db, doc.id, "user", target.id)
    await db.commit()
    assert await authz._document_grant_level(db, target.id, doc.id) is None
    assert not await authz.revoke_document_grant(db, doc.id, "user", target.id)


# ---------- 分享判定 ----------


@pytest.mark.asyncio
async def test_share_paths(db):
    owner = await make_user(db, "s-owner")
    writer = await make_user(db, "s-writer")
    doc = await make_doc(db, owner, "private")

    assert await authz.can_share_document(db, owner, doc)
    assert not await authz.can_share_document(db, writer, doc)  # 无授权
    # 持 document:share（user 内置角色）+ 可写 → 可再授权
    await authz.upsert_document_grant(db, doc.id, "user", writer.id, "write", owner.id)
    await db.commit()
    assert await authz.can_share_document(db, writer, doc)


# ---------- 可见性 SQL 条件（RAG / 列表共用） ----------


@pytest.mark.asyncio
async def test_visible_document_condition(db):
    owner = await make_user(db, "v-owner")
    member = await make_user(db, "v-member")
    other = await make_user(db, "v-other")
    admin = await make_user(db, "v-admin", "admin")
    own_doc = await make_doc(db, member, "private")
    team_doc = await make_doc(db, owner, "team")
    granted_doc = await make_doc(db, owner, "private")
    hidden_doc = await make_doc(db, owner, "private")
    group = await make_group(db, "v-dept", [member.id])
    await authz.upsert_document_grant(db, granted_doc.id, "group", group.id, "read", owner.id)
    await db.commit()

    async def visible_ids(user: User) -> set[uuid.UUID]:
        perms = await authz.get_user_permissions(db, user.id)
        cond = authz.visible_document_condition(user.id, perms)
        rows = (await db.execute(select(Document.id).where(cond))).scalars().all()
        return set(rows)

    member_ids = await visible_ids(member)
    assert member_ids == {own_doc.id, team_doc.id, granted_doc.id}
    other_ids = await visible_ids(other)
    assert other_ids == {team_doc.id}
    # read_all：全部文档可见
    admin_ids = await visible_ids(admin)
    assert {own_doc.id, team_doc.id, granted_doc.id, hidden_doc.id} <= admin_ids


# ---------- 权限缓存 ----------


@pytest.mark.asyncio
async def test_permission_cache_invalidation(db):
    user = await make_user(db, "c-user")
    assert await authz.get_user_permissions(db, user.id) == {"document:create", "document:share"}
    # 直接改库（模拟角色变更），未失效前命中缓存
    editor = (await db.execute(select(Role).where(Role.name == "editor"))).scalar_one()
    db.add(UserRole(user_id=user.id, role_id=editor.id))
    await db.commit()
    cached = await authz.get_user_permissions(db, user.id)
    authz.invalidate_permissions(user.id)
    fresh = await authz.get_user_permissions(db, user.id)
    assert fresh == cached  # editor 权限是 user 子集，值一致但路径走了失效后重查
    assert "document:create" in fresh
