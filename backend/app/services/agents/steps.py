"""AgentStep 步骤记录：SSE agent_step 事件与 messages.tool_call 留痕共用。

留痕复用 messages.tool_call JSON 字段（不改表结构）。该字段已有两套语义
（确认型 {id,name,args} / tool 结果型 {name,args,approved}），步骤留痕必须带
kind 判别键，避免污染前端确认 UI 与既有解析逻辑。
"""
from typing import Literal

from pydantic import BaseModel, Field


class AgentStep(BaseModel):
    """一个编排步骤（路由决策 / 计划 / 工具执行 / 校验结论）。"""

    step_type: Literal["router", "plan", "tool", "review"]
    agent: str  # 角色名：router/planner/executor/reviewer
    label: str  # 一句话摘要（前端时间线展示）
    status: Literal["running", "done", "failed", "skipped"]
    duration_ms: int = 0
    detail: dict = Field(default_factory=dict)  # 分类结果/计划内容/实际执行的工具名等


# messages.tool_call 留痕判别键：前端/历史加载按此区分步骤留痕与确认型 tool_call
STEPS_TRACE_KIND = "agent_steps"


def steps_to_trace(steps: list[AgentStep]) -> dict:
    """步骤序列序列化为 messages.tool_call 落库格式。"""
    return {"kind": STEPS_TRACE_KIND, "steps": [s.model_dump() for s in steps]}


def steps_from_trace(tool_call: dict | None) -> list[AgentStep]:
    """从 messages.tool_call 恢复步骤序列（历史消息时间线渲染路径）。

    两种留痕形态：
    - 纯留痕：{"kind": "agent_steps", "steps": [...]}（complete 消息）
    - 确认型+留痕：{"id","name","args", "agent_steps": [...]}（pending_confirm 消息，
      确认接口只读 name/args，agent_steps 键不影响既有契约）
    其他形态（tool 结果型/None）一律返回空列表。
    """
    if not isinstance(tool_call, dict):
        return []
    if tool_call.get("kind") == STEPS_TRACE_KIND:
        raw_steps = tool_call.get("steps")
    else:
        raw_steps = tool_call.get("agent_steps")
    if not isinstance(raw_steps, list):
        return []
    return [AgentStep.model_validate(s) for s in raw_steps]


def steps_key(steps: list[AgentStep]) -> dict:
    """生成确认型 tool_call 的留痕附加键：{"agent_steps": [...]}。"""
    return {"agent_steps": [s.model_dump() for s in steps]}
