"""Langfuse 追踪封装：LLM 调用/召回/重排的可观测性。

设计原则：
- 无 LANGFUSE_PUBLIC_KEY 或 SDK 未安装时自动禁用（no-op），不影响主流程
- 所有追踪调用内部容错（try/except），追踪失败绝不影响业务
- 以现有 traceId 作为 Langfuse trace 的 id，与应用日志可互相关联
"""
import logging
from contextlib import contextmanager

from app.config import get_settings

logger = logging.getLogger(__name__)

_client = None
_available: bool | None = None


def _get_client():
    """懒加载 Langfuse 客户端。不可用返回 None。"""
    global _client, _available
    if _available is False:
        return None
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        _available = False
        return None
    try:
        from langfuse import Langfuse  # 懒加载

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _available = True
        logger.info("langfuse tracing enabled: %s", settings.langfuse_host)
        return _client
    except Exception as exc:
        logger.warning("langfuse unavailable, tracing disabled: %s", exc)
        _available = False
        return None


def enabled() -> bool:
    return _get_client() is not None


@contextmanager
def trace_span(trace_id: str, name: str, metadata: dict | None = None):
    """追踪一个业务环节（retrieve/rerank/tool 等）。可用时记录，否则透传。"""
    client = _get_client()
    if client is None:
        yield None
        return
    span = None
    try:
        trace = client.trace(id=trace_id, name="chat")
        span = trace.span(name=name, metadata=metadata or {})
        yield span
    except Exception as exc:
        logger.debug("langfuse span error (%s): %s", name, exc)
        yield None
    finally:
        if span is not None:
            try:
                span.end()
            except Exception:
                pass


def trace_generation(
    trace_id: str,
    name: str,
    model: str,
    input_messages: list,
    output_text: str,
    usage: dict | None,
    metadata: dict | None = None,
) -> None:
    """记录一次 LLM 生成调用（含 token usage，供成本与质量分析）。容错不抛。"""
    client = _get_client()
    if client is None:
        return
    try:
        trace = client.trace(id=trace_id, name="chat")
        usage_detail = None
        if usage:
            usage_detail = {
                "input": usage.get("prompt_tokens", 0),
                "output": usage.get("completion_tokens", 0),
                "total": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            }
        trace.generation(
            name=name,
            model=model,
            input=input_messages,
            output=output_text[:2000],  # 截断避免超大 payload
            usage=usage_detail,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.debug("langfuse generation error: %s", exc)


def flush() -> None:
    """冲刷缓冲的追踪事件（worker/请求结束调用）。"""
    if _client is not None:
        try:
            _client.flush()
        except Exception:
            pass
