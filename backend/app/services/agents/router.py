"""Router Agent（L4）：LLM 查询分类路由，失败回退 L2 启发式（auto_top_k）。

- 分类 factual/list/comparison/summary → 代码侧映射 top_k（LLM 不直接产出数值，
  保持映射可控可评测）
- 结果缓存：(session_id, sha256(retrieval_query))，TTL 5 分钟，每 session 50 条 LRU；
  key 用改写后 query（Router 输入即改写后 query，语义一致且命中率高）
- 任何失败（超时/解析/schema 校验/网络）抛 RouterFallback，由调用方回退 L2
"""
import hashlib
import time
import uuid
from collections import OrderedDict
from typing import Literal

from pydantic import BaseModel

from app.services.agents.roles import AgentRole, RoleRunError
from app.services.agents.steps import AgentStep
from app.services.model_configs import ProviderConfig


class RouterFallback(Exception):
    """Router 失败，调用方回退 L2 启发式路由。可携带 failed 步骤记录。"""

    def __init__(self, message: str, step: AgentStep | None = None):
        super().__init__(message)
        self.step = step


class RouteDecision(BaseModel):
    """路由决策（LLM 分类 + 代码侧 top_k 映射）。"""

    category: Literal["factual", "list", "comparison", "summary"]
    top_k: int
    reason: str = ""


class _Classification(BaseModel):
    """LLM 实际输出 schema：只分类，top_k 由代码映射（可控可评测）。"""

    category: Literal["factual", "list", "comparison", "summary"]
    reason: str = ""


# 映射规则（与 L2 启发式档位对齐：narrow=3 / broad=10 / summary 介于中间）
_CATEGORY_TOP_K: dict[str, int] = {
    "factual": 3,
    "list": 10,
    "comparison": 10,
    "summary": 8,
}

_SYSTEM_PROMPT = (
    "你是检索路由分类器。把用户问题分成四类，决定知识库召回策略。分类标准：\n"
    "- factual：单点事实（时间/数字/是否/谁/怎么办），答案集中在 1-2 个片段\n"
    "- list：列举类（哪些/所有/清单/多少种），证据分散在多个片段\n"
    "- comparison：对比类（区别/差异/分别/对比），需要多份证据并列\n"
    "- summary：总结/汇总/框架/流程类，需要广泛召回后归纳\n"
    "只输出一行 JSON，不要输出任何解释：\n"
    '{"category": "factual|list|comparison|summary", "reason": "一句话分类依据"}'
)

router_role: AgentRole[_Classification] = AgentRole(
    name="router",
    output_schema=_Classification,
    system_prompt=_SYSTEM_PROMPT,
    max_tokens=100,  # 分类输出极短
)

# ---- 结果缓存：追问改写后 query 相同时避免重复分类 ----
_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_PER_SESSION = 50
_cache: OrderedDict[tuple[str, str], tuple[float, RouteDecision]] = OrderedDict()


def _cache_key(session_id: uuid.UUID, query: str) -> tuple[str, str]:
    digest = hashlib.sha256(query.strip().encode()).hexdigest()[:16]
    return (str(session_id), digest)


def _cache_get(session_id: uuid.UUID, query: str) -> RouteDecision | None:
    key = _cache_key(session_id, query)
    hit = _cache.get(key)
    if hit is None:
        return None
    ts, decision = hit
    if time.monotonic() - ts >= _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return decision


def _cache_put(session_id: uuid.UUID, query: str, decision: RouteDecision) -> None:
    key = _cache_key(session_id, query)
    _cache[key] = (time.monotonic(), decision)
    _cache.move_to_end(key)
    # 每 session LRU 上限：淘汰该 session 最久未命中条目
    session_keys = [k for k in _cache if k[0] == key[0]]
    while len(session_keys) > _CACHE_MAX_PER_SESSION:
        victim = session_keys.pop(0)
        _cache.pop(victim, None)


def reset_cache() -> None:
    """测试/运维用：清空全部缓存。"""
    _cache.clear()


async def route(
    provider: ProviderConfig,
    session_id: uuid.UUID,
    retrieval_query: str,
    *,
    trace_id: str | None = None,
    transport=None,
) -> tuple[RouteDecision, AgentStep, dict | None]:
    """LLM 查询分类路由。返回 (决策, 步骤记录, usage)；失败抛 RouterFallback。

    缓存命中时 usage 为 None（无新调用），步骤标记 cached=True。
    """
    cached = _cache_get(session_id, retrieval_query)
    if cached is not None:
        step = AgentStep(
            step_type="router", agent="router",
            label=f"分类为 {cached.category} → top_k={cached.top_k}（缓存）",
            status="done",
            detail={
                "category": cached.category, "top_k": cached.top_k,
                "reason": cached.reason, "cached": True,
            },
        )
        return cached, step, None

    try:
        cls, step, usage = await router_role.run(
            provider,
            f"【用户问题】{retrieval_query}",
            step_type="router", label="查询分类",
            trace_id=trace_id,
            trace_metadata={"retrieval_query": retrieval_query[:200]},
            transport=transport,
        )
    except RoleRunError as exc:
        raise RouterFallback(str(exc.cause), step=exc.step) from exc
    except Exception as exc:
        raise RouterFallback(str(exc)) from exc

    decision = RouteDecision(
        category=cls.category, top_k=_CATEGORY_TOP_K[cls.category], reason=cls.reason
    )
    step.label = f"分类为 {decision.category} → top_k={decision.top_k}"
    step.detail = {
        "category": decision.category, "top_k": decision.top_k,
        "reason": decision.reason, "cached": False,
    }
    _cache_put(session_id, retrieval_query, decision)
    return decision, step, usage
