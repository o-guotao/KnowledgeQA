"""agents 底座与 Router/编排单元测试。

底座：AgentStep 留痕序列化往返、AgentContext 预算追踪、AgentRole 执行协议。
Router 与编排循环用例随对应层级实现追加。
"""
import uuid

import httpx
import pytest
from pydantic import BaseModel

from app.services.agents import (
    AgentContext,
    AgentRole,
    AgentStep,
    steps_from_trace,
    steps_to_trace,
)
from app.services.llm_client import LLMStructureError
from app.services.model_configs import ProviderConfig


def _provider() -> ProviderConfig:
    return ProviderConfig(
        base_url="https://llm.example.com",
        model_name="test-model",
        api_key="sk-test",
        timeout_seconds=60.0,
        price_input_per_million=1.0,
        price_output_per_million=2.0,
    )


def _step(step_type: str = "router", status: str = "done") -> AgentStep:
    return AgentStep(
        step_type=step_type, agent="router", label="查询分类", status=status,
        duration_ms=120, detail={"category": "factual"},
    )


# ---------------- 底座：步骤留痕序列化 ----------------


def test_steps_trace_roundtrip():
    steps = [_step("router"), _step("plan", "skipped")]
    trace = steps_to_trace(steps)
    assert trace["kind"] == "agent_steps"
    restored = steps_from_trace(trace)
    assert [s.step_type for s in restored] == ["router", "plan"]
    assert restored[0].detail["category"] == "factual"


def test_steps_from_trace_ignores_foreign_kinds():
    # 确认型 / tool 结果型 / None 一律不误判为步骤留痕
    assert steps_from_trace({"id": "t1", "name": "delete_document", "args": {}}) == []
    assert steps_from_trace({"name": "list_documents", "auto": True}) == []
    assert steps_from_trace(None) == []
    assert steps_from_trace({"kind": "other", "steps": []}) == []


# ---------------- 底座：上下文预算追踪 ----------------


def test_context_usage_budget():
    ctx = AgentContext(
        user_id=uuid.uuid4(), session_id=uuid.uuid4(),
        query="q", retrieval_query="q",
    )
    assert ctx.add_usage({"prompt_tokens": 100, "completion_tokens": 50}) == 150
    assert ctx.add_usage(None) == 150
    assert ctx.add_usage({"prompt_tokens": 200, "completion_tokens": 0}) == 350
    assert not ctx.budget_exceeded(8000)
    assert ctx.budget_exceeded(300)


def test_context_evidence_two_kinds():
    ctx = AgentContext(
        user_id=uuid.uuid4(), session_id=uuid.uuid4(),
        query="q", retrieval_query="q",
    )
    ctx.add_evidence_chunks([("文档A.md", "内容甲"), ("文档B.md", "内容乙")])
    ctx.add_evidence_tool("list_documents", "文档清单…")
    kinds = [e.kind for e in ctx.evidence]
    assert kinds == ["chunk", "chunk", "tool"]
    assert ctx.evidence[2].source == "list_documents"


# ---------------- 底座：角色执行协议 ----------------


class _Decision(BaseModel):
    category: str
    top_k: int


def _role() -> AgentRole[_Decision]:
    return AgentRole(
        name="router", output_schema=_Decision,
        system_prompt="输出 JSON", max_tokens=100,
    )


@pytest.mark.asyncio
async def test_role_run_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"category": "list", "top_k": 10}'}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            },
        )

    parsed, step, usage = await _role().run(
        _provider(), "用户问题", step_type="router", label="查询分类",
        transport=httpx.MockTransport(handler),
    )

    assert parsed.category == "list"
    assert step.status == "done"
    assert step.agent == "router"
    assert usage == {"prompt_tokens": 20, "completion_tokens": 8}


@pytest.mark.asyncio
async def test_role_run_marks_step_failed_on_bad_output():
    from app.services.agents.roles import RoleRunError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "不是 JSON"}}]},
        )

    with pytest.raises(RoleRunError) as exc_info:
        await _role().run(
            _provider(), "用户问题", step_type="router", label="查询分类",
            transport=httpx.MockTransport(handler),
        )
    assert exc_info.value.step.status == "failed"
    assert isinstance(exc_info.value.cause, LLMStructureError)


# ---------------- Router Agent（L4） ----------------

from app.services.agents.router import RouterFallback, reset_cache, route  # noqa: E402


def _router_handler(category: str, calls: list) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": f'{{"category": "{category}", "reason": "测试"}}'}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 6},
            },
        )
    return handler


@pytest.mark.asyncio
async def test_router_maps_category_to_top_k_in_code():
    """top_k 由代码映射（LLM 不产出数值），四分类映射与档位对齐。"""
    reset_cache()
    calls: list = []
    decision, step, usage = await route(
        _provider(), uuid.uuid4(), "报销上限是多少",
        transport=httpx.MockTransport(_router_handler("factual", calls)),
    )
    assert decision.category == "factual"
    assert decision.top_k == 3  # factual→3，代码侧映射
    assert step.detail["cached"] is False
    assert usage == {"prompt_tokens": 30, "completion_tokens": 6}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_router_cache_hit_avoids_second_call():
    reset_cache()
    calls: list = []
    session = uuid.uuid4()
    transport = httpx.MockTransport(_router_handler("summary", calls))
    d1, _s1, _u1 = await route(_provider(), session, "总结一下请假制度", transport=transport)
    d2, s2, u2 = await route(_provider(), session, "总结一下请假制度", transport=transport)
    assert d2.category == d1.category == "summary"
    assert d2.top_k == 8  # summary→8
    assert len(calls) == 1  # 第二次走缓存
    assert s2.detail["cached"] is True
    assert u2 is None  # 缓存命中无新调用，不计费


@pytest.mark.asyncio
async def test_router_cache_key_is_rewritten_query():
    """缓存 key = 改写后 query：不同 query（即使同 session）不命中。"""
    reset_cache()
    calls: list = []
    session = uuid.uuid4()
    transport = httpx.MockTransport(_router_handler("list", calls))
    await route(_provider(), session, "公司有哪些福利", transport=transport)
    await route(_provider(), session, "福利还有哪些呢", transport=transport)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_router_fallback_on_bad_output():
    reset_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "无法分类"}}]})

    with pytest.raises(RouterFallback):
        await route(
            _provider(), uuid.uuid4(), "随便什么问题",
            transport=httpx.MockTransport(handler),
        )


# ---------------- 编排循环（orchestrator） ----------------

import json as _json  # noqa: E402

import app.services.agents.orchestrator as orc  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services.agents.orchestrator import (  # noqa: E402
    OrchestrationAborted,
    OrchestrationFallback,
    run_orchestrated,
)
from app.services.deepseek import StreamResult  # noqa: E402
from app.services.rag import RetrievedChunk  # noqa: E402


def _ctx() -> AgentContext:
    return AgentContext(
        user_id=uuid.uuid4(), session_id=uuid.uuid4(),
        query="报销上限是多少", retrieval_query="报销上限是多少",
    )


async def _no_disconnect() -> bool:
    return False


def _orch_handler(plan_content: str, review_content: str):
    """按 system prompt 分流 Planner/Reviewer 的 mock 响应。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = _json.loads(request.content)
        sys_prompt = body["messages"][0]["content"]
        content = plan_content if "规划器" in sys_prompt else review_content
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    return handler


async def _collect(gen) -> tuple[list, object]:
    events = []
    result = None
    async for kind, payload in gen:
        events.append((kind, payload))
        if kind == "result":
            result = payload
    return events, result


@pytest.mark.asyncio
async def test_orchestration_fallback_when_planner_fails():
    """Planner 首轮失败 → OrchestrationFallback（chat.py 回退旧回路）。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "无法规划"}}]})

    with pytest.raises(OrchestrationFallback):
        await _collect(run_orchestrated(
            _ctx(), _provider(), [{"role": "user", "content": "u"}], [],
            trace_id="t", is_client_gone=_no_disconnect,
            transport=httpx.MockTransport(handler),
        ))


@pytest.mark.asyncio
async def test_orchestration_direct_answer_with_sufficient_review():
    """计划一步 answer + Reviewer 判充分：无补充检索，正常产出 result。"""
    transport = httpx.MockTransport(_orch_handler(
        '{"steps": [{"type": "answer", "intent": "基于资料回答"}]}',
        '{"sufficient": true, "reason": "证据覆盖"}',
    ))
    events, result = await _collect(run_orchestrated(
        _ctx(), _provider(), [{"role": "user", "content": "u"}], [],
        trace_id="t", is_client_gone=_no_disconnect, transport=transport,
    ))
    assert result is not None
    assert result.extra_chunks == []
    assert result.pending_confirm is None
    step_types = [s.step_type for s in result.steps]
    assert step_types == ["plan", "review"]
    # Planner/Reviewer 的 usage 经 agent_usage 事件透出（供计费）
    agent_usages = [p for k, p in events if k == "agent_usage"]
    assert [r for r, _ in agent_usages] == ["planner", "reviewer"]


@pytest.mark.asyncio
async def test_orchestration_insufficient_triggers_supplementary_retrieve(monkeypatch):
    """Reviewer 判不足 → 补充检索一轮（证据与 extra_chunks 并入），之后不再 Reviewer。"""
    transport = httpx.MockTransport(_orch_handler(
        '{"steps": [{"type": "answer", "intent": "回答"}]}',
        '{"sufficient": false, "reason": "缺少具体数字"}',
    ))

    async def fake_embed(q):
        return [0.1] * 8

    async def fake_retrieve(db, user_id, vec, **kwargs):
        return [RetrievedChunk(uuid.uuid4(), uuid.uuid4(), "补充.md", "补充内容", 0.9)]

    monkeypatch.setattr(orc, "embed_query", fake_embed)
    monkeypatch.setattr(orc, "retrieve", fake_retrieve)

    _events, result = await _collect(run_orchestrated(
        _ctx(), _provider(), [{"role": "user", "content": "u"}], [],
        trace_id="t", is_client_gone=_no_disconnect, transport=transport,
    ))
    assert len(result.extra_chunks) == 1
    assert result.extra_chunks[0].document_name == "补充.md"
    step_types = [s.step_type for s in result.steps]
    # plan → review（不足）→ tool（补充检索）；无第二次 review（防循环）
    assert step_types == ["plan", "review", "tool"]


@pytest.mark.asyncio
async def test_orchestration_step_limit_skips(monkeypatch):
    """计划步骤数超过 AGENT_MAX_STEPS 时后续步骤 skipped。"""
    monkeypatch.setattr(get_settings(), "agent_max_steps", 1)
    transport = httpx.MockTransport(_orch_handler(
        '{"steps": ['
        '{"type": "retrieve", "intent": "再查一次"}, '
        '{"type": "retrieve", "intent": "又查一次"}, '
        '{"type": "answer", "intent": "回答"}'
        ']}',
        '{"sufficient": true, "reason": "ok"}',
    ))

    async def fake_embed(q):
        return [0.1] * 8

    async def fake_retrieve(db, user_id, vec, **kwargs):
        return []

    monkeypatch.setattr(orc, "embed_query", fake_embed)
    monkeypatch.setattr(orc, "retrieve", fake_retrieve)

    _events, result = await _collect(run_orchestrated(
        _ctx(), _provider(), [{"role": "user", "content": "u"}], [],
        trace_id="t", is_client_gone=_no_disconnect, transport=transport,
    ))
    statuses = [(s.step_type, s.status) for s in result.steps]
    assert ("tool", "done") in statuses  # 第一个 retrieve 执行
    assert ("tool", "skipped") in statuses  # 第二个 retrieve 被上限拦截


@pytest.mark.asyncio
async def test_orchestration_token_budget_skips_reviewer(monkeypatch):
    """Agent token 预算超限 → 跳过 Reviewer，直接用已有证据终答。"""
    monkeypatch.setattr(get_settings(), "agent_token_budget", 1)  # Planner 消耗即超限
    transport = httpx.MockTransport(_orch_handler(
        '{"steps": [{"type": "answer", "intent": "回答"}]}',
        '{"sufficient": true, "reason": "ok"}',
    ))
    _events, result = await _collect(run_orchestrated(
        _ctx(), _provider(), [{"role": "user", "content": "u"}], [],
        trace_id="t", is_client_gone=_no_disconnect, transport=transport,
    ))
    step_types = [s.step_type for s in result.steps]
    assert "review" not in step_types  # 预算超限，Reviewer 未执行


@pytest.mark.asyncio
async def test_orchestration_pending_confirm_on_delete(monkeypatch):
    """tool 步骤命中 REQUIRE_CONFIRM → pending_confirm 分流，编排终止（定案 A2）。"""
    transport = httpx.MockTransport(_orch_handler(
        '{"steps": [{"type": "tool", "intent": "删除报销制度文档"}, {"type": "answer", "intent": "总结"}]}',
        '{"sufficient": true, "reason": "ok"}',
    ))

    async def fake_stream_chat(provider, messages, tools=None):
        result = StreamResult()
        result.usage = {"prompt_tokens": 5, "completion_tokens": 3}
        result.tool_calls[0] = {
            "id": "call_1", "name": "delete_document",
            "arguments": '{"document_id": "11111111-1111-1111-1111-111111111111"}',
        }
        yield ("usage", None, result)
        yield ("tool_call", None, result)

    monkeypatch.setattr(orc, "stream_chat", fake_stream_chat)

    events, result = await _collect(run_orchestrated(
        _ctx(), _provider(), [{"role": "user", "content": "u"}], [],
        trace_id="t", is_client_gone=_no_disconnect, transport=transport,
    ))
    assert result.pending_confirm is not None
    assert result.pending_confirm["name"] == "delete_document"
    # Reviewer 不执行（pending 分流）；answer 步骤不执行（循环终止）
    step_types = [s.step_type for s in result.steps]
    assert "review" not in step_types
    # tool 步骤的 stream usage 经 usage 事件透出（供计费）
    assert any(k == "usage" for k, _ in events)


@pytest.mark.asyncio
async def test_orchestration_aborted_when_client_gone():
    """客户端断连 → OrchestrationAborted（不落库终答，消息置 aborted）。"""
    transport = httpx.MockTransport(_orch_handler(
        '{"steps": [{"type": "retrieve", "intent": "补充"}, {"type": "answer", "intent": "回答"}]}',
        '{"sufficient": true, "reason": "ok"}',
    ))

    async def _gone() -> bool:
        return True

    with pytest.raises(OrchestrationAborted):
        await _collect(run_orchestrated(
            _ctx(), _provider(), [{"role": "user", "content": "u"}], [],
            trace_id="t", is_client_gone=_gone, transport=transport,
        ))
