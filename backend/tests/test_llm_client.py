"""llm_client 单元测试：JSON 解析/schema 校验、重试策略、超时、usage 透传、json_mode。"""
import httpx
import pytest
from pydantic import BaseModel

from app.services.deepseek import ModelCallError, ModelTimeoutError
from app.services.llm_client import LLMStructureError, chat
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


def _ok_response(content: str, usage: dict | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


class _Decision(BaseModel):
    category: str
    top_k: int


@pytest.mark.asyncio
async def test_chat_returns_content_usage_messages():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response("你好")

    transport = httpx.MockTransport(handler)
    msgs = [{"role": "user", "content": "hi"}]
    result = await chat(_provider(), msgs, transport=transport)
    assert result.content == "你好"
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5}
    assert result.messages is msgs
    assert result.parsed is None


@pytest.mark.asyncio
async def test_chat_schema_parses_wrapped_json():
    def handler(request: httpx.Request) -> httpx.Response:
        # 模型输出前后带解释文字：宽容截取首尾大括号
        return _ok_response('分析结果：{"category": "factual", "top_k": 3} 以上')

    result = await chat(_provider(), [], schema=_Decision, transport=httpx.MockTransport(handler))
    assert result.parsed is not None
    assert result.parsed.category == "factual"
    assert result.parsed.top_k == 3


@pytest.mark.asyncio
async def test_chat_schema_rejects_non_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response("没有 JSON 的输出")

    with pytest.raises(LLMStructureError):
        await chat(_provider(), [], schema=_Decision, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_chat_schema_rejects_invalid_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_response('{"category": "factual", "top_k": "abc"}')

    with pytest.raises(LLMStructureError):
        await chat(_provider(), [], schema=_Decision, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_chat_retries_once_on_5xx():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return _ok_response("ok")

    result = await chat(_provider(), [], transport=httpx.MockTransport(handler))
    assert result.content == "ok"
    assert calls == 2


@pytest.mark.asyncio
async def test_chat_fails_after_second_5xx():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with pytest.raises(ModelCallError):
        await chat(_provider(), [], transport=httpx.MockTransport(handler))
    assert calls == 2


@pytest.mark.asyncio
async def test_chat_no_retry_on_4xx():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    with pytest.raises(ModelCallError):
        await chat(_provider(), [], transport=httpx.MockTransport(handler))
    assert calls == 1


@pytest.mark.asyncio
async def test_chat_timeout_raises_without_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModelTimeoutError):
        await chat(_provider(), [], transport=httpx.MockTransport(handler))
    assert calls == 1  # 超时不重试，避免双倍计费


@pytest.mark.asyncio
async def test_chat_json_mode_sets_response_format():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        seen["payload"] = _json.loads(request.content)
        return _ok_response("{}")

    await chat(
        _provider(), [], json_mode=True, schema=None,
        transport=httpx.MockTransport(handler),
    )
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["temperature"] == 0


@pytest.mark.asyncio
async def test_chat_timeout_cap_applied():
    """timeout_cap 小于 provider.timeout_seconds 时生效（体现在错误消息中的秒数）。"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModelTimeoutError, match=r"10\.0s"):
        await chat(
            _provider(), [], timeout_cap=10.0,
            transport=httpx.MockTransport(handler),
        )
