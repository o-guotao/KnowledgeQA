"""SSE 事件契约：可辨识联合（type 字段），与前端 zod schema 一一对应。"""
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    content: str = Field(min_length=1, max_length=8000)


class ChatEventBase(BaseModel):
    trace_id: str


class DeltaEvent(ChatEventBase):
    type: Literal["delta"] = "delta"
    content: str


class CitationEvent(ChatEventBase):
    type: Literal["citation"] = "citation"
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    snippet: str


class ToolCallEvent(ChatEventBase):
    type: Literal["tool_call"] = "tool_call"
    message_id: uuid.UUID
    tool_call_id: str
    name: str
    args: dict


class UsageEvent(ChatEventBase):
    type: Literal["usage"] = "usage"
    prompt_tokens: int
    completion_tokens: int
    cost_cny: float


class ErrorEvent(ChatEventBase):
    type: Literal["error"] = "error"
    code: Literal["TIMEOUT", "MODEL_ERROR", "ABORTED", "QUOTA_EXCEEDED", "INTERNAL"]
    message: str


class DoneEvent(ChatEventBase):
    type: Literal["done"] = "done"
    message_id: uuid.UUID


ChatEvent = Annotated[
    DeltaEvent | CitationEvent | ToolCallEvent | UsageEvent | ErrorEvent | DoneEvent,
    Field(discriminator="type"),
]
