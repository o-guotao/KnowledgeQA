"""文档 ACL 端点测试：grants 授权/撤销/列表、越权 404 语义、共享给我列表、/auth/me 权限点。

用 FastAPI 依赖覆盖把 get_db / get_current_user 接到内存 sqlite 与测试用户上，
httpx ASGITransport 与测试共用同一事件循环（避免 AsyncSession 跨 loop）。
"""
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api import auth as auth_api
from app.api import documents as documents_api
from app.core.errors import register_error_handlers
from app.core.security import get_current_user
from app.db import Base, get_db
from app.models.document import Document
from app.models.rbac import Role, UserRole
from app.models.user import User
from app.services import authorization as authz


def _build_app(session, current_user: User) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(documents_api.router, prefix="/api")
    app.include_router(auth_api.router, prefix="/api")

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    return app


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await authz.sync_rbac_catalog(s)
        yield s
    authz.invalidate_permissions()
    await engine.dispose()


async def _user(db, username: str, role_name: str = "user") -> User:
    user = User(username=username, password_hash="x")
    db.add(user)
    await db.flush()
    role = (await db.execute(select(Role).where(Role.name == role_name))).scalar_one()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.commit()
    authz.invalidate_permissions(user.id)
    return user


async def _doc(db, owner: User) -> Document:
    doc = Document(user_id=owner.id, filename=f"{uuid.uuid4().hex[:8]}.txt", object_key="k", status="ready")
    db.add(doc)
    await db.commit()
    return doc


@pytest.mark.asyncio
async def test_grant_lifecycle(session):
    owner = await _user(session, "owner")
    target = await _user(session, "target")
    doc = await _doc(session, owner)
    app = _build_app(session, owner)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        # 授予 read
        resp = await client.put(
            f"/api/documents/{doc.id}/grants",
            json={"grantee_type": "user", "grantee_id": str(target.id), "permission": "read"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["grantee_name"] == "target"

        # 升级为 write（upsert 覆盖）
        resp = await client.put(
            f"/api/documents/{doc.id}/grants",
            json={"grantee_type": "user", "grantee_id": str(target.id), "permission": "write"},
        )
        assert resp.status_code == 200

        # 列表：仅一条，最高权限 write
        resp = await client.get(f"/api/documents/{doc.id}/grants")
        assert resp.status_code == 200
        grants = resp.json()
        assert len(grants) == 1
        assert grants[0]["permission"] == "write"

        # 撤销
        resp = await client.delete(f"/api/documents/{doc.id}/grants/{grants[0]['id']}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/documents/{doc.id}/grants")
        assert resp.json() == []


@pytest.mark.asyncio
async def test_grants_forbidden_for_stranger(session):
    owner = await _user(session, "owner2")
    stranger = await _user(session, "stranger")
    doc = await _doc(session, owner)
    # stranger 视角：文档不可见，grants 端点统一 404（不泄露存在性）
    app = _build_app(session, stranger)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get(f"/api/documents/{doc.id}/grants")
        assert resp.status_code == 404
        resp = await client.put(
            f"/api/documents/{doc.id}/grants",
            json={"grantee_type": "user", "grantee_id": str(stranger.id), "permission": "read"},
        )
        assert resp.status_code == 404
        resp = await client.get(f"/api/documents/{doc.id}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_granted_user_can_read_and_shared_list(session):
    owner = await _user(session, "owner3")
    target = await _user(session, "target3")
    doc = await _doc(session, owner)
    await authz.upsert_document_grant(session, doc.id, "user", target.id, "read", owner.id)
    await session.commit()

    app = _build_app(session, target)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        # 被授权者可读文档详情
        resp = await client.get(f"/api/documents/{doc.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(doc.id)
        # 「共享给我」列表包含该文档
        resp = await client.get("/api/documents/shared")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert str(doc.id) in ids
        # 但 read 授权不可删除文档
        resp = await client.delete(f"/api/documents/{doc.id}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auth_me_returns_permissions(session):
    admin = await _user(session, "boss", "admin")
    app = _build_app(session, admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert "admin:user_manage" in body["permissions"]
        assert "document:read_all" in body["permissions"]
        assert body["roles"] == ["admin"]
