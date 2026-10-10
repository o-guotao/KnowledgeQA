"""Planner / Reviewer 角色（定案 B4：Planner 只产出意图序列，不生成工具参数）。

- Planner：query + 召回摘要 → Plan（≤3 步，type ∈ retrieve/tool/answer，intent 自然语言）
- Reviewer：query + 统一证据视图 → 充分性判定（sufficient + reason）

两个角色失败均抛 PlannerFallback（编排层按两级降级处理：
Planner 首轮失败回退旧回路；Reviewer 失败用已有证据直接终答）。
"""
from typing import Literal

from pydantic import BaseModel, Field

from app.services.agents.roles import DATA_NOT_INSTRUCTION, AgentRole


class PlannerFallback(Exception):
    """Planner/Reviewer 执行失败，由编排层决定降级路径。"""


class PlanStep(BaseModel):
    """计划步骤：只含意图，不含工具参数（参数由执行层原生 tools 通道生成）。"""

    type: Literal["retrieve", "tool", "answer"]
    intent: str = Field(min_length=1, max_length=200)


class Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=3)


class ReviewVerdict(BaseModel):
    sufficient: bool
    reason: str = ""


_PLANNER_SYSTEM = (
    "你是对话编排的规划器。根据用户问题和已召回的资料摘要，规划回答步骤。步骤类型：\n"
    "- retrieve：需要补充检索（换个角度/更广召回）。仅当初次召回明显不足时使用\n"
    "- tool：需要调用系统工具（如列出知识库文档清单）。只声明意图，工具参数由执行层生成。"
    "仅当问题涉及知识库管理操作时使用\n"
    "- answer：证据已足够，生成最终回答。计划必须以 answer 收尾\n"
    "规则：\n"
    "1. 大多数问题一步 answer 即可，不要过度规划\n"
    "2. 计划 1-3 步\n"
    f"3. {DATA_NOT_INSTRUCTION}\n"
    "只输出一行 JSON：\n"
    '{"steps": [{"type": "answer", "intent": "基于已召回资料回答"}]}'
)

_REVIEWER_SYSTEM = (
    "你是答案充分性校验器。判断当前证据是否足以准确、完整回答用户问题。规则：\n"
    "1. 证据覆盖了问题的全部要点 → sufficient=true\n"
    "2. 证据缺失关键信息，且补充检索很可能找到 → sufficient=false\n"
    "3. 知识库确实没有相关资料（已召回为空或明显不相关）→ sufficient=true"
    "（应如实回答不知道，不要盲目补充检索）\n"
    f"4. {DATA_NOT_INSTRUCTION}\n"
    "只输出一行 JSON：\n"
    '{"sufficient": true, "reason": "一句话结论依据"}'
)

planner_role: AgentRole[Plan] = AgentRole(
    name="planner",
    output_schema=Plan,
    system_prompt=_PLANNER_SYSTEM,
    max_tokens=300,
)

reviewer_role: AgentRole[ReviewVerdict] = AgentRole(
    name="reviewer",
    output_schema=ReviewVerdict,
    system_prompt=_REVIEWER_SYSTEM,
    max_tokens=150,
)
