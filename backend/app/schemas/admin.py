"""管理后台请求 / 响应模型。"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AdminUserMonth(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_cny: float
    limit_tokens: int


class AdminUserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    created_at: datetime
    month: AdminUserMonth


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=64)
    role: str = Field(default="user")  # user | admin


class AdminUserPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    role: str | None = None  # user | admin
    limit_tokens: int | None = Field(default=None, ge=0)
    password: str | None = Field(default=None, min_length=6, max_length=128)


class DailyUsage(BaseModel):
    date: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_cny: float


class UserUsage(BaseModel):
    user_id: uuid.UUID
    username: str
    calls: int
    total_tokens: int
    cost_cny: float


class ModelUsage(BaseModel):
    model: str
    calls: int
    total_tokens: int
    cost_cny: float
