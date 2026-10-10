"""AgentContext：编排循环内的共享状态。

生命周期 = chat 请求生命周期（定案 A2：不跨请求持久化）。
证据集统一两类：召回 chunk 与工具执行结果——Reviewer 的充分性校验面向
统一证据视图，不区分来源类型。
"""
import uuid
from dataclasses import dataclass, field
from typing import Literal

from app.services.agents.steps import AgentStep


@dataclass
class EvidenceItem:
    """一份证据：召回块内容或工具执行结果文本。"""

    kind: Literal["chunk", "tool"]
    text: str
    source: str = ""  # 文档名（chunk）或工具名（tool）


@dataclass
class AgentContext:
    """编排共享状态：身份、查询、证据、步骤轨迹、token 预算消耗。"""

    user_id: uuid.UUID
    session_id: uuid.UUID
    query: str  # 用户原始问题
    retrieval_query: str  # 改写后的检索 query（未改写时同 query）
    evidence: list[EvidenceItem] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    tokens_used: int = 0  # Agent 节点（Router/Planner/Reviewer）累计消耗，不含终答

    def add_evidence_chunks(self, chunks: list[tuple[str, str]]) -> None:
        """并入召回块。chunks 为 (文档名, 内容) 列表。"""
        for doc_name, content in chunks:
            self.evidence.append(EvidenceItem(kind="chunk", text=content, source=doc_name))

    def add_evidence_tool(self, tool_name: str, result_text: str) -> None:
        """并入工具执行结果。"""
        self.evidence.append(EvidenceItem(kind="tool", text=result_text, source=tool_name))

    def add_usage(self, usage: dict | None) -> int:
        """累计一个 Agent 节点的 token 消耗，返回当前总量。"""
        if usage:
            self.tokens_used += usage.get("prompt_tokens", 0) + usage.get(
                "completion_tokens", 0
            )
        return self.tokens_used

    def budget_exceeded(self, budget: int) -> bool:
        """Agent 节点开销是否超出预算（AGENT_TOKEN_BUDGET，不含终答）。"""
        return self.tokens_used >= budget
