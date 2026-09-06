import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ModelConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=8, max_length=512)
    model_name: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=1, max_length=512)
    timeout_seconds: float = Field(default=60.0, ge=1, le=300)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)
    price_input_per_million: float | None = Field(default=None, ge=0)
    price_output_per_million: float | None = Field(default=None, ge=0)

    @field_validator("name", "model_name", "api_key")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class ModelConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: str | None = Field(default=None, min_length=8, max_length=512)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    api_key: str | None = Field(default=None, min_length=1, max_length=512)
    timeout_seconds: float | None = Field(default=None, ge=1, le=300)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)
    price_input_per_million: float | None = Field(default=None, ge=0)
    price_output_per_million: float | None = Field(default=None, ge=0)


class ModelConfigOut(BaseModel):
    id: uuid.UUID
    name: str
    base_url: str
    model_name: str
    api_key_masked: str
    timeout_seconds: float
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    price_input_per_million: float | None
    price_output_per_million: float | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ModelConfigTestResult(BaseModel):
    ok: bool
    message: str
