"""Anthropic Messages API 适配层（Claude）。

把 Anthropic 协议翻译为与 openai_compatible.stream_chat 完全一致的三元组协议
（delta/usage/tool_call + StreamResult），调用方零改动：

- 请求侧：system 提取为顶层字段；OpenAI role:tool → tool_result 块；
  assistant.tool_calls → tool_use 块；连续同角色合并（Anthropic 要求严格交替）
- 响应侧：SSE 事件（text_delta/input_json_delta/message_delta）→ 三元组
- 重试/超时策略与 openai 版对齐：5xx/网络错误重试一次，超时不重试
- Anthropic 无 response_format / stream_options：JSON 结构化输出由 prompt
  指令 + llm_client 宽容解析兜底（优雅降级）

不引入 anthropic SDK，httpx 直连。
"""
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.services.deepseek import ModelCallError, ModelTimeoutError, StreamResult
from app.services.model_configs import ProviderConfig

logger = logging.getLogger(__name__)

# Anthropic API 版本头（后续需升级时改为 settings 配置项）
ANTHROPIC_VERSION = "2023-06-01"
# max_tokens 为 Anthropic 必填：provider 未配置时的兜底值
DEFAULT_MAX_TOKENS = 4096


def translate_tools(tools: list[dict] | None) -> list[dict] | None:
    """OpenAI function 格式 → Anthropic input_schema 格式。"""
    if not tools:
        return None
    out = []
    for t in tools:
        fn = t.get("function") or {}
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def translate_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI 内部消息格式 → (system 字符串, Anthropic messages 列表)。

    转换规则：
    - 全部 role:system 内容拼接为顶层 system（Anthropic 不接受 system 在 messages 内）
    - assistant.tool_calls → content blocks：text（可空）+ tool_use 块
    - role:tool（OpenAI 工具结果）→ 并入 user 消息的 tool_result 块
    - 连续同角色合并为一个消息的 blocks（Anthropic 要求 user/assistant 严格交替）
    """
    system_parts: list[str] = []
    converted: list[dict] = []  # [{"role": "user"|"assistant", "content": [blocks]}]

    def push(role: str, block: dict) -> None:
        if converted and converted[-1]["role"] == role:
            converted[-1]["content"].append(block)
        else:
            converted.append({"role": role, "content": [block]})

    for m in messages:
        role = m.get("role")
        if role == "system":
            if m.get("content"):
                system_parts.append(str(m["content"]))
            continue
        if role == "assistant":
            text = m.get("content") or ""
            if text:
                push("assistant", {"type": "text", "text": text})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    tool_input = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    tool_input = {}
                push("assistant", {
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": tool_input,
                })
            continue
        if role == "tool":
            # OpenAI 工具结果消息 → Anthropic tool_result 块（属于 user 角色）
            push("user", {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id", ""),
                "content": m.get("content") or "",
            })
            continue
        # user 普通文本
        if m.get("content"):
            push("user", {"type": "text", "text": str(m["content"])})

    # Anthropic 要求首条消息为 user：历史为空或首条为 assistant 时补空 user 占位
    if converted and converted[0]["role"] != "user":
        converted.insert(0, {"role": "user", "content": [{"type": "text", "text": "（接续对话）"}]})
    return "\n\n".join(system_parts), converted


def _headers(provider: ProviderConfig) -> dict:
    return {
        "x-api-key": provider.api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def _payload(
    provider: ProviderConfig, messages: list[dict],
    tools: list[dict] | None, max_tokens: int | None, stream: bool,
) -> dict:
    system, converted = translate_messages(messages)
    payload: dict = {
        "model": provider.model_name,
        "messages": converted,
        "max_tokens": max_tokens or provider.max_tokens or DEFAULT_MAX_TOKENS,
        "stream": stream,
    }
    if system:
        payload["system"] = system
    anthropic_tools = translate_tools(tools)
    if anthropic_tools:
        payload["tools"] = anthropic_tools
    for key, value in (("temperature", provider.temperature), ("top_p", provider.top_p)):
        if value is not None:
            payload[key] = value
    return payload


async def stream_chat(
    provider: ProviderConfig, messages: list[dict], tools: list[dict] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,  # 测试注入
) -> AsyncGenerator[tuple[str, dict | None, StreamResult], None]:
    """Anthropic 流式调用：事件翻译为与 openai 版一致的三元组。

    产出：(delta, 文本) → (usage, None) → [有工具调用时] (tool_call, None)。
    """
    payload = _payload(provider, messages, tools, max_tokens=None, stream=True)
    result = StreamResult()
    timeout = httpx.Timeout(provider.timeout_seconds, connect=10.0)
    url = f"{provider.base_url}/v1/messages"

    input_tokens = 0
    last_error: Exception | None = None
    for attempt in (1, 2):  # 5xx 重试一次；超时不重试
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                async with client.stream("POST", url, json=payload, headers=_headers(provider)) as response:
                    if response.status_code >= 500 and attempt == 1:
                        last_error = ModelCallError(f"anthropic {response.status_code}")
                        logger.warning("anthropic 5xx, retry once", extra={"event": "model_retry"})
                        continue
                    if response.status_code != 200:
                        raise ModelCallError(f"Anthropic 返回 {response.status_code}")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data:
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        etype = event.get("type")
                        if etype == "message_start":
                            usage = (event.get("message") or {}).get("usage") or {}
                            input_tokens = usage.get("input_tokens", 0)
                        elif etype == "content_block_start":
                            block = event.get("content_block") or {}
                            if block.get("type") == "tool_use":
                                result.tool_calls[event.get("index", 0)] = {
                                    "id": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "arguments": "",
                                }
                        elif etype == "content_block_delta":
                            delta = event.get("delta") or {}
                            if delta.get("type") == "text_delta" and delta.get("text"):
                                result.content_parts.append(delta["text"])
                                yield ("delta", delta["text"], result)
                            elif delta.get("type") == "input_json_delta":
                                slot = result.tool_calls.get(event.get("index", 0))
                                if slot is not None:
                                    slot["arguments"] += delta.get("partial_json", "")
                        elif etype == "message_delta":
                            usage = event.get("usage") or {}
                            result.usage = {
                                "prompt_tokens": input_tokens,
                                "completion_tokens": usage.get("output_tokens", 0),
                            }
            if result.usage is None:
                result.usage = {"prompt_tokens": input_tokens, "completion_tokens": 0}
            yield ("usage", None, result)
            if result.tool_calls:
                yield ("tool_call", None, result)
            return
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"模型调用超时（{provider.timeout_seconds}s）") from exc
        except httpx.HTTPError as exc:
            if attempt == 1:
                last_error = exc
                continue
            raise ModelCallError("模型服务网络错误") from exc
    raise ModelCallError(f"模型调用失败：{last_error}")


async def chat(
    provider: ProviderConfig,
    messages: list[dict],
    *,
    max_tokens: int,
    temperature: float | None = 0,
    timeout: httpx.Timeout,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, dict | None]:
    """Anthropic 非流式调用（供 llm_client 分发）。返回 (content, usage)。

    usage 映射：input_tokens → prompt_tokens，output_tokens → completion_tokens。
    """
    payload = _payload(provider, messages, tools=None, max_tokens=max_tokens, stream=False)
    if temperature is not None:
        payload["temperature"] = temperature
    url = f"{provider.base_url}/v1/messages"

    last_error: Exception | None = None
    for attempt in (1, 2):  # 5xx/网络错误重试一次（与 openai 路径对齐）；超时不重试
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await client.post(url, headers=_headers(provider), json=payload)
            if response.status_code >= 500 and attempt == 1:
                last_error = ModelCallError(f"anthropic provider {response.status_code}")
                continue
            if response.status_code != 200:
                raise ModelCallError(f"anthropic provider {response.status_code}")
            data = response.json()
            text = "".join(
                block.get("text", "")
                for block in data.get("content") or []
                if block.get("type") == "text"
            )
            raw_usage = data.get("usage") or {}
            usage = {
                "prompt_tokens": raw_usage.get("input_tokens", 0),
                "completion_tokens": raw_usage.get("output_tokens", 0),
            }
            return text, usage
        except httpx.TimeoutException:
            raise  # 由 llm_client 转换为 ModelTimeoutError
        except httpx.HTTPError as exc:
            if attempt == 1:
                last_error = exc
                continue
            raise ModelCallError(f"anthropic 网络错误：{exc}") from exc
    raise ModelCallError(f"anthropic 调用失败：{last_error}")


async def test_connection(provider: ProviderConfig) -> None:
    """最小请求验证连通性（max_tokens=1）。"""
    timeout = httpx.Timeout(provider.timeout_seconds, connect=10.0)
    payload = {
        "model": provider.model_name,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "ping"}]}],
        "max_tokens": 1,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{provider.base_url}/v1/messages", headers=_headers(provider), json=payload
        )
    if response.status_code < 200 or response.status_code >= 300:
        raise ModelCallError("provider connection failed")
