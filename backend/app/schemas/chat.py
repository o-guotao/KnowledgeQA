"""SSE 事件契约：可辨识联合（type 字段），与前端 zod schema 一一对应。"""
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    content: str = Field(min_length=1, max_length=8000)
    # 检索片段数：不传则用服务端默认 rag_top_k；允许前端按需调整召回数量
    top_k: int | None = Field(default=None, ge=1, le=20)


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


class AgentStepEvent(ChatEventBase):
    """编排步骤事件：路由决策/计划/工具执行/校验结论。

    按实际发生顺序发送（Router 决策在召回之前，其 step 先于 citation 出现）；
    字段与 services/agents/steps.AgentStep 平铺对应（避免 schemas 依赖 services）。
    """

    type: Literal["agent_step"] = "agent_step"
    step_type: Literal["router", "plan", "tool", "review"]
    agent: str
    label: str
    status: Literal["running", "done", "failed", "skipped"]
    duration_ms: int = 0
    detail: dict = Field(default_factory=dict)

    @classmethod
    def from_step(cls, trace_id: str, step) -> "AgentStepEvent":
        return cls(
            trace_id=trace_id, step_type=step.step_type, agent=step.agent,
            label=step.label, status=step.status,
            duration_ms=step.duration_ms, detail=step.detail,
        )


ChatEvent = Annotated[
    DeltaEvent | CitationEvent | ToolCallEvent | UsageEvent | ErrorEvent | DoneEvent | AgentStepEvent,
    Field(discriminator="type"),
]
