"""SSE 流式对话：服务端代理 DeepSeek，前端禁止直连模型。

事件流（可辨识联合，见 schemas/chat.py）：
citation* -> delta* -> (tool_call -> done) | (usage -> done) | error

DB 策略：流开始前建立 assistant 记录拿到 id；流期间只读；
收尾统一用 UPDATE 语句落库（content/citations/usage/status），
避免 ORM 对象跨会话共享的生命周期问题。
"""
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update
from sse_starlette.sse import EventSourceResponse

from app.core.security import get_current_user
from app.core.errors import AppError
from app.db import SessionLocal
from app.logging_config import get_trace_id, set_trace_id
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    CitationEvent,
    DeltaEvent,
    DoneEvent,
    ErrorEvent,
    ToolCallEvent,
    UsageEvent,
)
from app.services import cost, injection, langfuse_tracing
from app.services.deepseek import ModelCallError, ModelTimeoutError
from app.services.embedding import embed_query
from app.services.rag import build_rag_prompt, retrieve
from app.services.model_configs import ProviderConfig, resolve_provider_config
from app.services.openai_compatible import stream_chat
from app.services.tools import REQUIRE_CONFIRM, TOOL_DEFINITIONS, execute_tool, parse_tool_args

logger = logging.getLogger(__name__)
router = APIRouter()

HISTORY_LIMIT = 20


def _sse(event) -> dict:
    return {"data": event.model_dump_json()}


async def _load_history(session_id: uuid.UUID) -> list[dict]:
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Message)
                .where(Message.session_id == session_id, Message.status == "complete")
                .order_by(Message.created_at.desc())
                .limit(HISTORY_LIMIT)
            )
        ).scalars().all()
    history = []
    for m in reversed(rows):
        if m.role == "user":
            history.append({"role": "user", "content": m.content})
        elif m.role == "assistant" and m.content:
            history.append({"role": "assistant", "content": m.content})
    return history


async def _finish_message(message_id: uuid.UUID, **values) -> None:
    async with SessionLocal() as db:
        await db.execute(update(Message).where(Message.id == message_id).values(**values))
        await db.commit()


class _ClientGone(Exception):
    pass


async def _event_stream(
    request: Request, body: ChatRequest, user: User, trace_id: str
) -> AsyncGenerator[dict, None]:
    assistant_id: uuid.UUID | None = None
    content_parts: list[str] = []
    citations: list[dict] = []

    async def fail(code: str, message: str, event_message: str) -> AsyncGenerator[dict, None]:
        if assistant_id is not None:
            await _finish_message(
                assistant_id, status="failed", error=f"{code}: {message}",
                content="".join(content_parts),
            )
        yield _sse(ErrorEvent(trace_id=trace_id, code=code, message=event_message))

    try:
        # ---- 前置校验与用户消息落库 ----
        async with SessionLocal() as db:
            session = (
                await db.execute(
                    select(Session).where(Session.id == body.session_id, Session.user_id == user.id)
                )
            ).scalar_one_or_none()
            if session is None:
                yield _sse(ErrorEvent(trace_id=trace_id, code="INTERNAL", message="会话不存在"))
                return
            if await cost.quota_exhausted(db, user.id):
                yield _sse(
                    ErrorEvent(trace_id=trace_id, code="QUOTA_EXCEEDED", message="本月 token 配额已用尽")
                )
                return
            db.add(Message(session_id=session.id, role="user", content=body.content, trace_id=trace_id))
            if session.title == "新会话":
                session.title = body.content[:24]
            assistant = Message(session_id=session.id, role="assistant", status="streaming", trace_id=trace_id)
            db.add(assistant)
            await db.commit()
            await db.refresh(assistant)
            assistant_id = assistant.id

        history = await _load_history(body.session_id)
        async with SessionLocal() as db:
            provider: ProviderConfig = await resolve_provider_config(db, user.id)

        # ---- RAG 召回（按用户隔离），失败降级为空召回 ----
        with langfuse_tracing.trace_span(trace_id, "retrieve", {"query": body.content[:200]}):
            try:
                query_vec = await embed_query(body.content)
                async with SessionLocal() as db:
                    chunks = await retrieve(db, user.id, query_vec, query_text=body.content)
            except Exception as exc:
                logger.warning("retrieve degraded: %s", exc, extra={"event": "rag_degraded"})
                chunks = []
        injection.scan_chunks([c.content for c in chunks])

        for c in chunks:
            citations.append({
                "chunk_id": str(c.chunk_id), "document_id": str(c.document_id),
                "document_name": c.document_name, "score": c.score,
            })
            yield _sse(CitationEvent(
                trace_id=trace_id, chunk_id=c.chunk_id, document_id=c.document_id,
                document_name=c.document_name, snippet=c.content[:120],
            ))

        # history 末尾是刚落库的当前用户消息，替换为 RAG 包装版本
        messages = history[:-1] + [{"role": "user", "content": build_rag_prompt(body.content, chunks)}]

        # ---- 模型流式调用（工具回路最多 2 轮） ----
        # 每轮 stream_chat 末尾会 yield usage（含工具调用轮）；
        # usage 事件到达即累计费用，避免工具回路/确认路径漏算 token。
        accumulated_prompt = 0
        accumulated_completion = 0
        usage: dict | None = None
        for round_no in range(2):
            has_tool_call = False
            async for kind, payload, result in stream_chat(
                provider, messages, tools=TOOL_DEFINITIONS if round_no == 0 else None
            ):
                if await request.is_disconnected():
                    raise _ClientGone()
                if kind == "delta":
                    content_parts.append(payload or "")
                    yield _sse(DeltaEvent(trace_id=trace_id, content=payload or ""))
                elif kind == "usage":
                    u = result.usage or {}
                    p, c = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
                    accumulated_prompt += p
                    accumulated_completion += c
                    usage = {"prompt_tokens": accumulated_prompt, "completion_tokens": accumulated_completion}
                    cost_cny_round = cost.compute_cost_cny(
                        p, c, provider.price_input_per_million, provider.price_output_per_million
                    )
                    async with SessionLocal() as db:
                        await cost.accumulate_usage(db, user.id, p, c)
                        await db.commit()
                    yield _sse(UsageEvent(
                        trace_id=trace_id, prompt_tokens=p,
                        completion_tokens=c, cost_cny=cost_cny_round,
                    ))
                elif kind == "tool_call":
                    has_tool_call = True
                    auto: list[tuple[dict, str]] = []
                    pending: dict | None = None
                    for tc in result.ordered_tool_calls:
                        if tc["name"] in REQUIRE_CONFIRM:
                            pending = tc
                        else:
                            async with SessionLocal() as db:
                                res = await execute_tool(db, user.id, tc["name"], parse_tool_args(tc["arguments"]))
                                await db.commit()
                            auto.append((tc, res))

                    if pending is not None:
                        args = parse_tool_args(pending["arguments"])
                        await _finish_message(
                            assistant_id, status="pending_confirm", content=result.content,
                            citations=citations,
                            tool_call={"id": pending["id"], "name": pending["name"], "args": args},
                            usage={**(usage or {}), "cost_cny": cost.compute_cost_cny(accumulated_prompt, accumulated_completion, provider.price_input_per_million, provider.price_output_per_million)} if usage else None,
                        )
                        yield _sse(ToolCallEvent(
                            trace_id=trace_id, message_id=assistant_id,
                            tool_call_id=pending["id"], name=pending["name"], args=args,
                        ))
                        yield _sse(DoneEvent(trace_id=trace_id, message_id=assistant_id))
                        return

                    messages.append({
                        "role": "assistant",
                        "content": result.content or None,
                        "tool_calls": [
                            {"id": tc["id"], "type": "function",
                             "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                            for tc, _ in auto
                        ],
                    })
                    async with SessionLocal() as db:
                        for tc, res in auto:
                            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": res})
                            db.add(Message(
                                session_id=body.session_id, role="tool", content=res,
                                trace_id=trace_id, tool_call={"name": tc["name"], "auto": True},
                            ))
                        await db.commit()
                elif kind == "usage":
                    usage = result.usage
            if not has_tool_call:
                break

        # ---- 正常收尾：汇总 usage 落到消息记录，完成态 ----
        # 费用已在每次 usage 事件到达时累计，此处不再重复累加。
        cost_cny = cost.compute_cost_cny(
            accumulated_prompt, accumulated_completion,
            provider.price_input_per_million, provider.price_output_per_million,
        ) if usage else 0.0
        await _finish_message(
            assistant_id, status="complete", content="".join(content_parts),
            citations=citations,
            usage={**(usage or {}), "cost_cny": cost_cny} if usage else None,
        )
        # Langfuse 记录完整生成（输出 + token usage），供成本与质量分析
        langfuse_tracing.trace_generation(
            trace_id, "chat_completion", provider.model_name, messages,
            "".join(content_parts), usage,
            metadata={"session_id": str(body.session_id), "citations": len(citations)},
        )
        langfuse_tracing.flush()
        yield _sse(DoneEvent(trace_id=trace_id, message_id=assistant_id))

    except _ClientGone:
        if assistant_id is not None:
            await _finish_message(assistant_id, status="aborted", content="".join(content_parts))
        logger.info("client aborted stream", extra={"event": "stream_aborted"})
    except ModelTimeoutError as exc:
        async for event in fail("TIMEOUT", str(exc), "模型响应超时，请稍后重试"):
            yield event
    except ModelCallError as exc:
        async for event in fail("MODEL_ERROR", str(exc), "模型服务异常，请稍后重试"):
            yield event
    except AppError as exc:
        async for event in fail("MODEL_ERROR", exc.message, exc.message):
            yield event
    except Exception as exc:
        logger.exception("chat stream failed", extra={"event": "stream_error"})
        async for event in fail("INTERNAL", str(exc)[:300], "服务内部错误，已记录 traceId"):
            yield event


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> EventSourceResponse:
    trace_id = get_trace_id()
    set_trace_id(trace_id)
    return EventSourceResponse(
        _event_stream(request, body, user, trace_id),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        ping=15,
    )
