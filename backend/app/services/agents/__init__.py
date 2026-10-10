"""多 Agent 编排包：Router（L4 查询路由）与 Planner-Executor-Reviewer 编排循环。

设计原则：
- 每个 Agent 角色 = AgentRole（roles.py），输出 Pydantic 强校验
- 共享状态 = AgentContext（context.py），生命周期 = chat 请求
- 步骤轨迹 = AgentStep（steps.py），贯穿 SSE 事件与 messages.tool_call 留痕
- 所有节点失败抛异常由编排层降级，绝不影响主链路可用性
"""
from app.services.agents.context import AgentContext, EvidenceItem
from app.services.agents.roles import DATA_NOT_INSTRUCTION, AgentRole, wrap_evidence
from app.services.agents.steps import (
    STEPS_TRACE_KIND,
    AgentStep,
    steps_from_trace,
    steps_to_trace,
)

__all__ = [
    "AgentContext",
    "AgentRole",
    "AgentStep",
    "DATA_NOT_INSTRUCTION",
    "EvidenceItem",
    "STEPS_TRACE_KIND",
    "steps_from_trace",
    "steps_to_trace",
    "wrap_evidence",
]
