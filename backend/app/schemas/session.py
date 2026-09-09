import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = Field(default="新会话", max_length=128)


class SessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=128)


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    status: str
    trace_id: str
    citations: list | None
    tool_call: dict | None
    usage: dict | None
    error: str | None
    feedback: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
