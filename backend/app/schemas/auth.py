import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    """开放注册：密码强度校验在端点内做（同 PasswordChange 的理由，422 形状不利于透出文案）。"""
    username: str = Field(min_length = 1, max_length = 64)
    password: str = Field(min_length = 1, max_length = 128)
    display_name: str = Field(default="", max_length=64)

class PasswordChange(BaseModel):
    """修改密码：长度校验在端点内做（422 的错误形状不利于前端透出友好文案）。"""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
