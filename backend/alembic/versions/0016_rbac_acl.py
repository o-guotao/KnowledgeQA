"""细粒度权限：RBAC（角色/权限点）+ 用户组 + 文档级 ACL 授权表

Revision ID: 0016_rbac_acl
Revises: 0015_memory_system
Create Date: 2026-10-08
"""
import uuid

import sqlalchemy as sa
from alembic import op

from app.core.permissions import BUILTIN_ROLES, LEGACY_ROLE_MAP, PERMISSION_CATALOG

revision = "0016_rbac_acl"
down_revision = "0015_memory_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(256), server_default="", nullable=False),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("description", sa.String(256), server_default="", nullable=False),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Uuid(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    op.create_table(
        "groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(256), server_default="", nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_groups_name", "groups", ["name"], unique=True)

    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])

    op.create_table(
        "document_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("grantee_type", sa.String(8), nullable=False),
        sa.Column("grantee_id", sa.Uuid(), nullable=False),
        sa.Column("permission", sa.String(8), server_default="read", nullable=False),
        sa.Column("granted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "grantee_type", "grantee_id", name="uq_document_grants_target"),
    )
    op.create_index("ix_document_grants_document_id", "document_grants", ["document_id"])
    op.create_index("ix_document_grants_grantee", "document_grants", ["grantee_type", "grantee_id"])

    _seed_builtin_rbac()


def _seed_builtin_rbac() -> None:
    """初始化权限点目录、内置角色及其权限，并按旧 users.role 列回填 user_roles。"""
    roles_tbl = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_builtin", sa.Boolean),
    )
    perms_tbl = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    role_perms_tbl = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    user_roles_tbl = sa.table(
        "user_roles",
        sa.column("user_id", sa.Uuid()),
        sa.column("role_id", sa.Uuid()),
    )

    perm_ids: dict[str, uuid.UUID] = {}
    for code, desc in PERMISSION_CATALOG.items():
        perm_ids[code] = uuid.uuid4()
    op.bulk_insert(
        perms_tbl,
        [{"id": perm_ids[code], "code": code, "description": desc} for code, desc in PERMISSION_CATALOG.items()],
    )

    role_ids: dict[str, uuid.UUID] = {}
    role_perm_rows = []
    for name, (desc, codes) in BUILTIN_ROLES.items():
        rid = uuid.uuid4()
        role_ids[name] = rid
        for code in codes:
            role_perm_rows.append({"role_id": rid, "permission_id": perm_ids[code]})
    op.bulk_insert(
        roles_tbl,
        [
            {"id": rid, "name": name, "description": BUILTIN_ROLES[name][0], "is_builtin": True}
            for name, rid in role_ids.items()
        ],
    )
    if role_perm_rows:
        op.bulk_insert(role_perms_tbl, role_perm_rows)

    # 按旧 users.role 列回填用户角色（未知值兜底为 user 角色）
    conn = op.get_bind()
    users_tbl = sa.table(
        "users", sa.column("id", sa.Uuid()), sa.column("role", sa.String)
    )
    rows = conn.execute(sa.select(users_tbl.c.id, users_tbl.c.role)).all()
    default_role = role_ids["user"]
    op.bulk_insert(
        user_roles_tbl,
        [
            {"user_id": uid, "role_id": role_ids.get(LEGACY_ROLE_MAP.get(role or "", "user"), default_role)}
            for uid, role in rows
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_document_grants_grantee", table_name="document_grants")
    op.drop_index("ix_document_grants_document_id", table_name="document_grants")
    op.drop_table("document_grants")
    op.drop_index("ix_group_members_user_id", table_name="group_members")
    op.drop_table("group_members")
    op.drop_index("ix_groups_name", table_name="groups")
    op.drop_table("groups")
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_roles_name", table_name="roles")
    op.drop_table("roles")
