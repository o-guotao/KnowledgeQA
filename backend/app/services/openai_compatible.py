"""OpenAI Chat Completions 兼容服务的安全流式客户端。"""
import json
from collections.abc import AsyncGenerator

import httpx

from app.services.deepseek import ModelCallError, ModelTimeoutError, StreamResult
from app.services.model_configs import ProviderConfig


async def test_provider_connection(provider: ProviderConfig) -> None:
    """发起一个最小请求；调用方只暴露统一成功/失败信息。"""
    timeout = httpx.Timeout(provider.timeout_seconds, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{provider.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {provider.api_key}"},
            json={"model": provider.model_name, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
        )
    if response.status_code < 200 or response.status_code >= 300:
        raise ModelCallError("provider connection failed")


async def stream_chat(
    provider: ProviderConfig, messages: list[dict], tools: list[dict] | None = None
) -> AsyncGenerator[tuple[str, dict | None, StreamResult], None]:
    payload: dict = {"model": provider.model_name, "messages": messages, "stream": True, "stream_options": {"include_usage": True}}
    if tools:
        payload["tools"] = tools
    # 推理参数可选：None = 不传，使用模型服务端默认值
    for key, value in (
        ("temperature", provider.temperature),
        ("top_p", provider.top_p),
        ("max_tokens", provider.max_tokens),
    ):
        if value is not None:
            payload[key] = value
    result = StreamResult()
    timeout = httpx.Timeout(provider.timeout_seconds, connect=10.0)
    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{provider.base_url}/chat/completions", json=payload, headers={"Authorization": f"Bearer {provider.api_key}"}) as response:
                    if response.status_code >= 500 and attempt == 1:
                        last_error = ModelCallError(f"provider {response.status_code}")
                        continue
                    if response.status_code != 200:
                        raise ModelCallError(f"模型服务返回 {response.status_code}")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("usage"):
                            result.usage = {"prompt_tokens": chunk["usage"].get("prompt_tokens", 0), "completion_tokens": chunk["usage"].get("completion_tokens", 0)}
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta") or {}
                            if delta.get("content"):
                                result.content_parts.append(delta["content"])
                                yield ("delta", delta["content"], result)
                            for tc in delta.get("tool_calls") or []:
                                slot = result.tool_calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                                if tc.get("id"):
                                    slot["id"] = tc["id"]
                                function = tc.get("function") or {}
                                if function.get("name"):
                                    slot["name"] = function["name"]
                                if function.get("arguments"):
                                    slot["arguments"] += function["arguments"]
            if result.usage is None:
                result.usage = {"prompt_tokens": 0, "completion_tokens": 0}
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
