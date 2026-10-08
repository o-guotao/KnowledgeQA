"""权限点目录与内置角色定义。

代码常量为唯一权威来源；迁移与启动时 upsert 入表（services/authorization.py 的
sync_rbac_catalog），保证代码与数据库一致。
"""

# 权限点目录：code -> 描述
PERMISSION_CATALOG: dict[str, str] = {
    "document:create": "上传/创建文档",
    "document:share": "共享文档（对个人/用户组授权）",
    "document:read_all": "查看全部文档（含他人私有文档）",
    "document:team_manage": "管理团队空间文档（编辑/删除团队文档）",
    "admin:user_manage": "用户管理",
    "admin:role_manage": "角色与权限管理",
    "admin:group_manage": "用户组管理",
    "admin:eval": "评测中心",
}

ALL_PERMISSIONS = tuple(PERMISSION_CATALOG.keys())

# 内置角色：name -> (描述, 权限点列表)。内置角色不可删除。
BUILTIN_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": ("系统管理员，拥有全部权限", list(ALL_PERMISSIONS)),
    "user": ("普通用户，可上传与共享文档", ["document:create", "document:share"]),
    "editor": ("编辑者，可上传文档", ["document:create"]),
    "viewer": ("只读用户，仅可查看有权限的文档", []),
}

# 旧 users.role 列值 -> 内置角色名 的映射（向后兼容）
LEGACY_ROLE_MAP: dict[str, str] = {"admin": "admin", "user": "user"}
