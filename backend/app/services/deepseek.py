"""DeepSeek 流式客户端：OpenAI 兼容协议，密钥仅存在于本服务端模块。

- stream=true + stream_options.include_usage=true，流末尾返回 usage
- httpx 超时 → ModelTimeoutError；5xx 重试一次后 → ModelCallError
"""
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class ModelTimeoutError(Exception):
    pass


class ModelCallError(Exception):
    pass


@dataclass
class StreamResult:
    """一次流式调用的聚合结果，由调用方在迭代过程中逐步填充。"""

    content_parts: list[str] = field(default_factory=list)
    tool_calls: dict[int, dict] = field(default_factory=dict)  # index -> {id,name,arguments}
    usage: dict | None = None  # {prompt_tokens, completion_tokens}

    @property
    def content(self) -> str:
        return "".join(self.content_parts)

    @property
    def ordered_tool_calls(self) -> list[dict]:
        return [self.tool_calls[i] for i in sorted(self.tool_calls)]


async def stream_chat(
    messages: list[dict], tools: list[dict] | None = None
) -> AsyncGenerator[tuple[str, dict | None, StreamResult], None]:
    """流式调用 DeepSeek。

    产出三元组 (kind, payload, result)：
    - ("delta", "文本", result)：增量文本
    - ("tool_call", None, result)：流结束且模型请求工具调用，result.ordered_tool_calls 有效
    - ("usage", None, result)：流正常结束，result.usage 有效
    """
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ModelCallError("服务端未配置 DEEPSEEK_API_KEY")

    payload: dict = {
        "model": settings.deepseek_model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        payload["tools"] = tools

    result = StreamResult()
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
    timeout = httpx.Timeout(settings.deepseek_timeout_seconds, connect=10.0)

    last_error: Exception | None = None
    for attempt in (1, 2):  # 5xx 重试一次
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{settings.deepseek_base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code >= 500 and attempt == 1:
                        last_error = ModelCallError(f"DeepSeek {response.status_code}")
                        logger.warning("deepseek 5xx, retry once", extra={"event": "model_retry"})
                        continue
                    if response.status_code != 200:
                        body = (await response.aread())[:300]
                        raise ModelCallError(f"DeepSeek 返回 {response.status_code}: {body!r}")

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
                            result.usage = {
                                "prompt_tokens": chunk["usage"].get("prompt_tokens", 0),
                                "completion_tokens": chunk["usage"].get("completion_tokens", 0),
                            }
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta") or {}
                            if delta.get("content"):
                                result.content_parts.append(delta["content"])
                                yield ("delta", delta["content"], result)
                            for tc in delta.get("tool_calls") or []:
                                slot = result.tool_calls.setdefault(
                                    tc.get("index", 0), {"id": "", "name": "", "arguments": ""}
                                )
                                if tc.get("id"):
                                    slot["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] = fn["name"]
                                if fn.get("arguments"):
                                    slot["arguments"] += fn["arguments"]

            if result.tool_calls:
                yield ("tool_call", None, result)
            else:
                yield ("usage", None, result)
            return
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"模型调用超时（{settings.deepseek_timeout_seconds}s）") from exc
        except httpx.HTTPError as exc:
            if attempt == 1:
                last_error = exc
                continue
            raise ModelCallError(f"网络错误：{exc}") from exc

    raise ModelCallError(f"模型调用失败：{last_error}")
