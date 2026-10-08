"""RBAC / 用户组 / 文档授权 的请求响应模型。"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------- 权限点 / 角色 ----------
class PermissionOut(BaseModel):
    code: str
    description: str


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    is_builtin: bool
    permissions: list[str] = []
    member_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=256)
    permissions: list[str] | None = None


class UserRolesUpdate(BaseModel):
    """整体替换用户的角色集合。"""

    role_ids: list[uuid.UUID] = []


# ---------- 用户组 ----------
class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    owner_id: uuid.UUID | None
    owner_name: str | None = None
    member_count: int = 0
    created_at: datetime


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=256)


class GroupMemberOut(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str


class GroupMemberAdd(BaseModel):
    user_id: uuid.UUID


# ---------- 文档授权（ACL） ----------
class GrantOut(BaseModel):
    id: uuid.UUID
    grantee_type: str  # user | group
    grantee_id: uuid.UUID
    grantee_name: str = ""
    permission: str  # read | write
    created_at: datetime


class GrantUpsert(BaseModel):
    grantee_type: str = Field(pattern="^(user|group)$")
    grantee_id: uuid.UUID
    permission: str = Field(pattern="^(read|write)$")


# ---------- 主体搜索（共享弹窗/组成员添加） ----------
class UserBrief(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str


class GroupBrief(BaseModel):
    id: uuid.UUID
    name: str


class PrincipalSearchOut(BaseModel):
    users: list[UserBrief] = []
    groups: list[GroupBrief] = []
