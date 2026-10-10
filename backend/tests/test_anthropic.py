"""Anthropic 适配层单元测试：消息/tools 翻译、流式事件翻译、非流式调用、llm_client 分发。"""
import httpx
import pytest
from pydantic import BaseModel

from app.services.anthropic import chat, stream_chat, translate_messages, translate_tools
from app.services.deepseek import ModelCallError, ModelTimeoutError
from app.services.llm_client import LLMStructureError
from app.services.llm_client import chat as llm_chat
from app.services.model_configs import ProviderConfig


def _provider() -> ProviderConfig:
    return ProviderConfig(
        base_url="https://api.anthropic.com",
        model_name="claude-sonnet-4-5",
        api_key="sk-ant-test",
        timeout_seconds=60.0,
        price_input_per_million=3.0,
        price_output_per_million=15.0,
        protocol="anthropic",
    )


def _sse(lines: list[str]) -> httpx.Response:
    body = "\n\n".join(f"data: {line}" for line in lines) + "\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


# ---------------- 消息翻译 ----------------


def test_translate_messages_extracts_system():
    system, msgs = translate_messages([
        {"role": "system", "content": "规则一"},
        {"role": "system", "content": "规则二"},
        {"role": "user", "content": "问题"},
    ])
    assert system == "规则一\n\n规则二"
    assert msgs == [{"role": "user", "content": [{"type": "text", "text": "问题"}]}]


def test_translate_messages_merges_consecutive_same_role():
    _system, msgs = translate_messages([
        {"role": "user", "content": "第一句"},
        {"role": "user", "content": "第二句"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "追问"},
    ])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert len(msgs[0]["content"]) == 2  # 连续 user 合并为 blocks


def test_translate_messages_assistant_tool_calls_to_tool_use():
    _system, msgs = translate_messages([
        {"role": "user", "content": "列出文档"},
        {
            "role": "assistant",
            "content": "好的",
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "list_documents", "arguments": "{}"},
            }],
        },
    ])
    assistant = msgs[1]
    assert assistant["role"] == "assistant"
    types = [b["type"] for b in assistant["content"]]
    assert types == ["text", "tool_use"]
    tool_use = assistant["content"][1]
    assert tool_use["id"] == "call_1"
    assert tool_use["name"] == "list_documents"
    assert tool_use["input"] == {}


def test_translate_messages_tool_result_becomes_user_block():
    _system, msgs = translate_messages([
        {"role": "user", "content": "列出文档"},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_1", "type": "function",
            "function": {"name": "list_documents", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "call_1", "content": "文档清单…"},
        {"role": "user", "content": "继续"},
    ])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    # assistant 无文本时只有 tool_use 块
    assert [b["type"] for b in msgs[1]["content"]] == ["tool_use"]
    # tool 结果转为 user 角色的 tool_result 块，并与后续 user 文本合并为一条消息
    assert msgs[2]["content"][0] == {
        "type": "tool_result", "tool_use_id": "call_1", "content": "文档清单…",
    }
    assert msgs[2]["content"][1] == {"type": "text", "text": "继续"}


def test_translate_messages_first_must_be_user():
    _system, msgs = translate_messages([{"role": "assistant", "content": "先说"}])
    assert msgs[0]["role"] == "user"


def test_translate_tools_function_to_input_schema():
    tools = [{
        "type": "function",
        "function": {
            "name": "delete_document",
            "description": "删除文档",
            "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}},
        },
    }]
    out = translate_tools(tools)
    assert out == [{
        "name": "delete_document",
        "description": "删除文档",
        "input_schema": {"type": "object", "properties": {"document_id": {"type": "string"}}},
    }]
    assert translate_tools(None) is None


# ---------------- 流式事件翻译 ----------------


@pytest.mark.asyncio
async def test_stream_chat_text_flow():
    def handler(request: httpx.Request) -> httpx.Response:
        return _sse([
            '{"type":"message_start","message":{"usage":{"input_tokens":25}}}',
            '{"type":"content_block_start","index":0,"content_block":{"type":"text"}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"你好"}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"世界"}}',
            '{"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":7}}',
            '{"type":"message_stop"}',
        ])

    events = []
    async for kind, payload, result in stream_chat(
        _provider(), [{"role": "user", "content": "hi"}],
        transport=httpx.MockTransport(handler),
    ):
        events.append((kind, payload))
    kinds = [k for k, _ in events]
    assert kinds == ["delta", "delta", "usage"]
    assert result.content == "你好世界"
    assert result.usage == {"prompt_tokens": 25, "completion_tokens": 7}


@pytest.mark.asyncio
async def test_stream_chat_tool_use_flow():
    def handler(request: httpx.Request) -> httpx.Response:
        return _sse([
            '{"type":"message_start","message":{"usage":{"input_tokens":30}}}',
            '{"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"toolu_1","name":"list_documents"}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"a\\":"}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"1}"}}',
            '{"type":"content_block_stop","index":0}',
            '{"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":12}}',
            '{"type":"message_stop"}',
        ])

    events = []
    async for kind, payload, result in stream_chat(
        _provider(), [{"role": "user", "content": "列表"}],
        tools=[{"type": "function", "function": {"name": "list_documents", "description": "", "parameters": {}}}],
        transport=httpx.MockTransport(handler),
    ):
        events.append((kind, payload))
    kinds = [k for k, _ in events]
    # 事件顺序与 openai 版一致：usage 先于 tool_call
    assert kinds == ["usage", "tool_call"]
    tc = result.ordered_tool_calls[0]
    assert tc["id"] == "toolu_1"
    assert tc["name"] == "list_documents"
    assert tc["arguments"] == '{"a":1}'


@pytest.mark.asyncio
async def test_stream_chat_retries_once_on_5xx():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(529)
        return _sse([
            '{"type":"message_start","message":{"usage":{"input_tokens":1}}}',
            '{"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":1}}',
        ])

    events = []
    async for kind, _p, _r in stream_chat(
        _provider(), [{"role": "user", "content": "hi"}],
        transport=httpx.MockTransport(handler),
    ):
        events.append(kind)
    assert calls == 2
    assert events == ["usage"]


@pytest.mark.asyncio
async def test_stream_chat_timeout_not_retried():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModelTimeoutError):
        async for _ in stream_chat(
            _provider(), [{"role": "user", "content": "hi"}],
            transport=httpx.MockTransport(handler),
        ):
            pass
    assert calls == 1


# ---------------- 非流式调用 ----------------


@pytest.mark.asyncio
async def test_chat_non_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "content": [
                {"type": "text", "text": "第一部分"},
                {"type": "tool_use", "id": "x", "name": "y", "input": {}},
                {"type": "text", "text": "第二部分"},
            ],
            "usage": {"input_tokens": 11, "output_tokens": 6},
        })

    content, usage = await chat(
        _provider(), [{"role": "user", "content": "hi"}], max_tokens=100,
        temperature=0, timeout=httpx.Timeout(10.0),
        transport=httpx.MockTransport(handler),
    )
    assert content == "第一部分第二部分"
    assert usage == {"prompt_tokens": 11, "completion_tokens": 6}


@pytest.mark.asyncio
async def test_chat_retries_once_on_5xx_fails_on_4xx():
    calls_5xx = 0

    def handler_5xx(request: httpx.Request) -> httpx.Response:
        nonlocal calls_5xx
        calls_5xx += 1
        return httpx.Response(500)

    with pytest.raises(ModelCallError):
        await chat(
            _provider(), [], max_tokens=1, temperature=0,
            timeout=httpx.Timeout(10.0), transport=httpx.MockTransport(handler_5xx),
        )
    assert calls_5xx == 2

    calls_4xx = 0

    def handler_4xx(request: httpx.Request) -> httpx.Response:
        nonlocal calls_4xx
        calls_4xx += 1
        return httpx.Response(400)

    with pytest.raises(ModelCallError):
        await chat(
            _provider(), [], max_tokens=1, temperature=0,
            timeout=httpx.Timeout(10.0), transport=httpx.MockTransport(handler_4xx),
        )
    assert calls_4xx == 1


# ---------------- llm_client 分发 ----------------


class _Out(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_llm_client_dispatches_anthropic_with_schema():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": '结果：{"answer": "可以"} 以上'}],
            "usage": {"input_tokens": 9, "output_tokens": 4},
        })

    result = await llm_chat(
        _provider(), [{"role": "user", "content": "问"}],
        schema=_Out, json_mode=True,  # json_mode 在 anthropic 下优雅降级为宽容解析
        transport=httpx.MockTransport(handler),
    )
    assert result.parsed is not None
    assert result.parsed.answer == "可以"
    assert result.usage == {"prompt_tokens": 9, "completion_tokens": 4}


@pytest.mark.asyncio
async def test_llm_client_anthropic_schema_failure_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "没有 JSON"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    with pytest.raises(LLMStructureError):
        await llm_chat(
            _provider(), [{"role": "user", "content": "问"}],
            schema=_Out, transport=httpx.MockTransport(handler),
        )
