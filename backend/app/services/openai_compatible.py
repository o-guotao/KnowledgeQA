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


class _MarkupFilter:
    """剥离 content 中模型泄露的 DSML / 伪工具调用标记（跨 chunk 安全）。

    真正的工具调用走 ``delta.tool_calls`` 结构化通道；content 里出现的
    ``<｜｜DSML｜｜`` / ``<|DSML|`` 段是模型对未定义工具的"伪调用"，
    原样透出会污染界面（用户可见原始标记），故在流出前剔除。
    """

    STARTS = ("<｜｜DSML｜｜", "<|DSML|")
    END = "/tool_calls"
    _TAIL = 16  # 起始标记跨 chunk 判定时的缓冲尾长

    def __init__(self) -> None:
        self._buf = ""
        self._skip = False

    def feed(self, text: str) -> str:
        self._buf += text
        out: list[str] = []
        while self._buf:
            if self._skip:
                end = self._buf.find(self.END)
                if end == -1:
                    self._buf = self._buf[-len(self.END):]  # 结束标记可能跨 chunk，保留尾部
                    break
                self._buf = self._buf[end + len(self.END):]
                if self._buf.startswith(">"):  # 吞掉 DSML 段收尾的 '>'
                    self._buf = self._buf[1:]
                self._skip = False
                continue
            starts = [i for i in (self._buf.find(s) for s in self.STARTS) if i != -1]
            idx = min(starts) if starts else -1
            if idx == -1:
                if len(self._buf) > self._TAIL:  # 末尾可能是起始前缀，保留尾巴
                    out.append(self._buf[:-self._TAIL])
                    self._buf = self._buf[-self._TAIL:]
                break
            out.append(self._buf[:idx])
            self._buf = self._buf[idx:]
            if not any(self._buf.startswith(s) for s in self.STARTS):
                break  # 起始标记未完整，等下一 chunk
            self._skip = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self._skip else self._buf
        self._buf = ""
        return rest


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
    markup_filter = _MarkupFilter()
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
                                clean = markup_filter.feed(delta["content"])
                                if clean:
                                    result.content_parts.append(clean)
                                    yield ("delta", clean, result)
                            for tc in delta.get("tool_calls") or []:
                                slot = result.tool_calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                                if tc.get("id"):
                                    slot["id"] = tc["id"]
                                function = tc.get("function") or {}
                                if function.get("name"):
                                    slot["name"] = function["name"]
                                if function.get("arguments"):
                                    slot["arguments"] += function["arguments"]
            # 冲刷过滤器残余的正常文本（流末尾不属于任何标记段的尾巴）
            tail = markup_filter.flush()
            if tail:
                result.content_parts.append(tail)
                yield ("delta", tail, result)
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
