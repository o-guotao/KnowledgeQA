"""编排循环：Planner → Executor → Reviewer（async generator，chat.py 消费转发）。

事件协议（与 stream_chat 三元组风格一致）：
- ("step", AgentStep)：步骤状态变更（running/done/failed/skipped），chat.py 转发 SSE
- ("delta", str)：tool 步骤的流式文本（转发给用户，与现有回路行为一致）
- ("usage", dict)：tool 步骤 stream_chat 的 token usage（chat.py 计费）
- ("result", OrchestrationResult)：编排结束（终态，恰好一次）

硬限制（防失控）：
- 计划步骤数 ≤ settings.agent_max_steps（计计划步骤数）
- Agent 节点 token 预算 settings.agent_token_budget（仅 Planner/Reviewer，不含终答）
- 单 Agent 节点超时 settings.agent_step_timeout（AgentRole 内生效）
- LLM 调用次数自然上限：Planner 1 + Reviewer ≤2 + 每 tool 步骤 1 + 终答 1

两级降级：
- Planner 首轮失败 → 抛 OrchestrationFallback（chat.py 回退现有 range(2) 回路）
- 编排中途异常/预算超限 → 中断，用已收集证据正常返回（调用方直接终答）

断连：每步骤边界检查 is_client_gone()，命中抛 OrchestrationAborted
（已收集证据不落库为终答，消息状态 aborted，与 _ClientGone 语义对齐）。
"""
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.db import SessionLocal
from app.models.message import Message
from app.services import injection
from app.services.agents.context import AgentContext
from app.services.agents.planner import Plan, ReviewVerdict, planner_role, reviewer_role
from app.services.agents.roles import RoleRunError, wrap_evidence
from app.services.agents.steps import AgentStep
from app.services.embedding import embed_query
from app.services.openai_compatible import stream_chat
from app.services.rag import RetrievedChunk, retrieve
from app.services.tools import REQUIRE_CONFIRM, TOOL_DEFINITIONS, execute_tool, parse_tool_args

logger = logging.getLogger(__name__)

# 补充检索的固定召回量（broad 档位）
_RETRIEVE_STEP_TOP_K = 10
# Reviewer 证据视图：最多 10 份、每份截断 300 字（控制 token 预算）
_REVIEW_MAX_EVIDENCE = 10
_REVIEW_EVIDENCE_CHARS = 300


class OrchestrationFallback(Exception):
    """Planner 首轮失败：chat.py 回退现有 range(2) 工具回路。"""


class OrchestrationAborted(Exception):
    """客户端断连：编排中止，消息置 aborted（不落库终答）。"""


@dataclass
class OrchestrationResult:
    """编排产物：补充证据、工具消息序列、确认分流信号、步骤轨迹。"""

    extra_chunks: list[RetrievedChunk] = field(default_factory=list)
    tool_messages: list[dict] = field(default_factory=list)  # 追加到终答 messages 尾部
    pending_confirm: dict | None = None  # {id,name,args}，非 None 时走确认收尾（定案 A2）
    steps: list[AgentStep] = field(default_factory=list)


def _planner_input(query: str, chunks: list[RetrievedChunk]) -> str:
    lines = [f"【用户问题】{query}", "", "【已召回资料摘要】"]
    if not chunks:
        lines.append("（未召回任何资料）")
    for c in chunks[:8]:
        lines.append(f"- {c.document_name}：{c.content[:120]}")
    return "\n".join(lines)


def _reviewer_input(ctx: AgentContext) -> str:
    lines = [f"【用户问题】{ctx.query}", "", "【当前证据】"]
    if not ctx.evidence:
        lines.append("（无）")
    for e in ctx.evidence[:_REVIEW_MAX_EVIDENCE]:
        tag = "资料" if e.kind == "chunk" else "工具结果"
        lines.append(f"- [{tag}·{e.source}] {wrap_evidence(e.text[:_REVIEW_EVIDENCE_CHARS])}")
    return "\n".join(lines)


async def _supplementary_retrieve(
    ctx: AgentContext, result: OrchestrationResult, query_text: str, label: str
) -> AgentStep:
    """补充检索：embed → retrieve → 注入检测 → 并入证据与结果。失败不中断编排。"""
    step = AgentStep(step_type="tool", agent="executor", label=label, status="running")
    try:
        vec = await embed_query(query_text)
        async with SessionLocal() as db:
            new_chunks = await retrieve(
                db, ctx.user_id, vec,
                top_k=_RETRIEVE_STEP_TOP_K, query_text=query_text, adaptive_k=True,
            )
        injection.scan_chunks([c.content for c in new_chunks])
        result.extra_chunks.extend(new_chunks)
        ctx.add_evidence_chunks([(c.document_name, c.content) for c in new_chunks])
        step.status = "done"
        step.detail = {"chunks": len(new_chunks)}
    except Exception as exc:
        logger.warning("orchestration retrieve degraded: %s", exc,
                       extra={"event": "orchestration_retrieve_degraded"})
        step.status = "failed"
        step.detail = {"error": str(exc)[:100]}
    return step


async def run_orchestrated(
    ctx: AgentContext,
    provider,
    messages: list[dict],
    chunks: list[RetrievedChunk],
    *,
    trace_id: str,
    is_client_gone: Callable[[], Awaitable[bool]],
    transport=None,
) -> AsyncGenerator[tuple[str, Any], None]:
    """编排循环入口（chat.py 唯一调用点）。产出事件流，终态为 ("result", ...)。"""
    settings = get_settings()
    budget = settings.agent_token_budget
    max_steps = settings.agent_max_steps
    result = OrchestrationResult()

    # ---- 1. Planner：首轮失败 → 抛 OrchestrationFallback 回退旧回路 ----
    yield ("step", AgentStep(
        step_type="plan", agent="planner", label="正在规划回答步骤…", status="running",
    ))
    try:
        plan: Plan
        plan, pstep, pusage = await planner_role.run(
            provider, _planner_input(ctx.query, chunks),
            step_type="plan", label="规划回答步骤",
            trace_id=trace_id, transport=transport,
        )
    except RoleRunError as exc:
        exc.step.label = "规划失败，回退常规回答"
        yield ("step", exc.step)
        raise OrchestrationFallback(str(exc.cause)) from exc
    ctx.add_usage(pusage)
    yield ("agent_usage", ("planner", pusage))
    pstep.label = f"计划 {len(plan.steps)} 步：" + " → ".join(s.type for s in plan.steps)
    pstep.detail = {"steps": [s.model_dump() for s in plan.steps]}
    result.steps.append(pstep)
    yield ("step", pstep)
    logger.info(
        "orchestration plan: %d steps",
        len(plan.steps),
        extra={"event": "orchestration_plan",
               "extra": {"steps": [s.type for s in plan.steps]}},
    )

    # ---- 2. Executor：逐步执行（步数/预算/断连硬限制） ----
    executed = 0
    pending: dict | None = None
    for ps in plan.steps:
        if ps.type == "answer" or pending is not None:
            break
        if executed >= max_steps or ctx.budget_exceeded(budget):
            skip = AgentStep(
                step_type="tool", agent="executor",
                label=f"跳过 {ps.type} 步骤（达到编排上限）", status="skipped",
            )
            result.steps.append(skip)
            yield ("step", skip)
            break
        if await is_client_gone():
            raise OrchestrationAborted()

        if ps.type == "retrieve":
            executed += 1
            yield ("step", AgentStep(
                step_type="tool", agent="executor",
                label=f"补充检索：{ps.intent[:30]}", status="running",
            ))
            step = await _supplementary_retrieve(
                ctx, result, ps.intent, f"补充检索：{ps.intent[:30]}"
            )
            step.detail["intent"] = ps.intent
            result.steps.append(step)
            yield ("step", step)
            continue

        # tool 步骤：原生 tools 通道生成参数（定案 B4）
        executed += 1
        step = AgentStep(
            step_type="tool", agent="executor",
            label=f"工具调用：{ps.intent[:30]}", status="running",
            detail={"intent": ps.intent},
        )
        yield ("step", step)
        tool_messages = messages + [
            {"role": "user", "content": f"请基于以上信息执行以下操作：{ps.intent}"}
        ]
        auto_tcs: list[tuple[dict, str]] = []
        try:
            async for kind, payload, sres in stream_chat(
                provider, tool_messages, tools=TOOL_DEFINITIONS
            ):
                if await is_client_gone():
                    raise OrchestrationAborted()
                if kind == "delta":
                    yield ("delta", payload or "")
                elif kind == "usage":
                    yield ("usage", sres.usage or {})
                elif kind == "tool_call":
                    for tc in sres.ordered_tool_calls:
                        if tc["name"] in REQUIRE_CONFIRM:
                            pending = {
                                "id": tc["id"], "name": tc["name"],
                                "args": parse_tool_args(tc["arguments"]),
                            }
                            break
                        async with SessionLocal() as db:
                            res = await execute_tool(
                                db, ctx.user_id, tc["name"], parse_tool_args(tc["arguments"])
                            )
                            # 工具结果落库留痕（与现有回路 {name, auto} 格式一致）
                            db.add(Message(
                                session_id=ctx.session_id, role="tool", content=res,
                                trace_id=trace_id,
                                tool_call={"name": tc["name"], "auto": True},
                            ))
                            await db.commit()
                        auto_tcs.append((tc, res))
                        ctx.add_evidence_tool(tc["name"], res)
                    if pending is not None:
                        break  # 命中确认闸门即终止当前流，走确认收尾（定案 A2）
            if auto_tcs:
                result.tool_messages.append({
                    "role": "assistant",
                    "content": sres.content or None,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc, _ in auto_tcs
                    ],
                })
                for tc, res in auto_tcs:
                    result.tool_messages.append(
                        {"role": "tool", "tool_call_id": tc["id"], "content": res}
                    )
            step.status = "done"
            step.detail["tools"] = [tc["name"] for tc, _ in auto_tcs]
            if pending is not None:
                step.detail["pending_confirm"] = pending["name"]
                step.label = f"待确认：{pending['name']}"
        except OrchestrationAborted:
            raise
        except Exception as exc:
            logger.warning("orchestration tool step degraded: %s", exc,
                           extra={"event": "orchestration_tool_degraded"})
            step.status = "failed"
            step.detail["error"] = str(exc)[:100]
        result.steps.append(step)
        yield ("step", step)

    # ---- 3. Reviewer：充分性校验（pending/预算超限时跳过；失败直接终答） ----
    if pending is None and not ctx.budget_exceeded(budget):
        yield ("step", AgentStep(
            step_type="review", agent="reviewer", label="正在校验证据充分性…", status="running",
        ))
        try:
            verdict: ReviewVerdict
            verdict, rstep, rusage = await reviewer_role.run(
                provider, _reviewer_input(ctx),
                step_type="review", label="校验证据充分性",
                trace_id=trace_id, transport=transport,
            )
            ctx.add_usage(rusage)
            yield ("agent_usage", ("reviewer", rusage))
            rstep.label = "证据充分" if verdict.sufficient else "证据不足"
            rstep.detail = {"sufficient": verdict.sufficient, "reason": verdict.reason}
            result.steps.append(rstep)
            yield ("step", rstep)
            logger.info(
                "orchestration review: sufficient=%s", verdict.sufficient,
                extra={"event": "orchestration_review",
                       "extra": {"sufficient": verdict.sufficient, "reason": verdict.reason[:100]}},
            )
            # 不足且步数有余量 → 补充检索一轮（之后不再 Reviewer，防循环）
            if not verdict.sufficient and executed < max_steps:
                if await is_client_gone():
                    raise OrchestrationAborted()
                gap_query = verdict.reason.strip() or ctx.retrieval_query
                step = await _supplementary_retrieve(
                    ctx, result, gap_query, "补充检索（校验后）"
                )
                result.steps.append(step)
                yield ("step", step)
        except OrchestrationAborted:
            raise
        except RoleRunError as exc:
            exc.step.label = "校验失败，直接生成回答"
            result.steps.append(exc.step)
            yield ("step", exc.step)

    result.pending_confirm = pending
    yield ("result", result)
