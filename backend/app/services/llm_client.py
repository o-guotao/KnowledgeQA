"""统一非流式 LLM client：Agent 角色与辅助 LLM 调用的唯一入口。

职责：
- 基于 ProviderConfig 的非流式 chat 调用（OpenAI 兼容协议）
- 可选 JSON 结构化输出：response_format=json_object + 宽容截取 + Pydantic 校验
- 超时：min(provider.timeout_seconds, timeout_cap)，connect 固定 10s
- 重试：仅 5xx / 网络错误重试一次；超时不重试（与 stream_chat 语义对齐，
  避免超时重试造成的双倍计费）
- 可选 Langfuse 埋点（trace_id + trace_name 同时传入时记录）
- 失败一律抛异常（ModelCallError / ModelTimeoutError / LLMStructureError），
  由调用方决定降级策略——本模块不做静默兜底

调用方约定：schema 传入时模型必须输出 JSON 对象；prompt 中需明示 JSON 格式
（json_mode 只开协议侧约束，不替代 prompt 指令）。
"""
import json
import logging
from dataclasses import dataclass, field
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.services import langfuse_tracing
from app.services.deepseek import ModelCallError, ModelTimeoutError
from app.services.model_configs import ProviderConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMStructureError(Exception):
    """JSON 结构化输出解析或 schema 校验失败。"""


@dataclass
class LLMCallResult:
    """一次非流式调用的聚合结果。"""

    content: str  # 模型原始输出文本
    usage: dict | None = None  # {prompt_tokens, completion_tokens}（供计费）
    messages: list[dict] = field(default_factory=list)  # 调用入参（供 tracing）
    parsed: BaseModel | None = None  # schema 校验通过的结构化输出


def _extract_json_object(raw: str) -> dict:
    """宽容截取模型输出中的 JSON 对象（首尾大括号之间）并 loads。"""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise LLMStructureError("模型输出中未找到 JSON 对象")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMStructureError(f"模型输出 JSON 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise LLMStructureError("模型输出不是 JSON 对象")
    return data


async def chat(
    provider: ProviderConfig,
    messages: list[dict],
    *,
    schema: type[T] | None = None,
    json_mode: bool = False,
    max_tokens: int = 500,
    temperature: float = 0,
    timeout_cap: float = 30.0,
    trace_id: str | None = None,
    trace_name: str | None = None,
    trace_metadata: dict | None = None,
    transport: httpx.AsyncBaseTransport | None = None,  # 测试注入
) -> LLMCallResult:
    """非流式 chat 调用。schema 传入时对输出做 Pydantic 强校验（parsed 字段）。

    timeout_cap 为节点级超时上限（实际超时 = min(provider.timeout_seconds, timeout_cap)），
    防止辅助调用串行在主链路上吃光整体预算。
    """
    # 协议适配层分流：anthropic 走 Messages API（json_mode 优雅降级为 prompt 指令
    # + 宽容解析兜底；重试策略在 anthropic.chat 内与 openai 路径对齐）
    if provider.protocol == "anthropic":
        from app.services.anthropic import chat as anthropic_chat

        timeout_seconds = min(provider.timeout_seconds, timeout_cap)
        try:
            content, usage = await anthropic_chat(
                provider, messages, max_tokens=max_tokens, temperature=temperature,
                timeout=httpx.Timeout(timeout_seconds, connect=10.0),
                transport=transport,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"llm 调用超时（{timeout_seconds}s）") from exc
        result = LLMCallResult(content=content, usage=usage, messages=messages)
        if schema is not None:
            try:
                result.parsed = schema.model_validate(_extract_json_object(content))
            except ValidationError as exc:
                raise LLMStructureError(f"模型输出未通过 schema 校验：{exc}") from exc
        if trace_id and trace_name:
            langfuse_tracing.trace_generation(
                trace_id, trace_name, provider.model_name, messages,
                content, result.usage, metadata=trace_metadata,
            )
        return result

    payload: dict = {
        "model": provider.model_name,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    timeout_seconds = min(provider.timeout_seconds, timeout_cap)
    timeout = httpx.Timeout(timeout_seconds, connect=10.0)
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    url = f"{provider.base_url}/chat/completions"

    last_error: Exception | None = None
    for attempt in (1, 2):  # 5xx / 网络错误重试一次；超时不重试
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 500 and attempt == 1:
                last_error = ModelCallError(f"llm provider {response.status_code}")
                logger.warning(
                    "llm_client 5xx, retry once",
                    extra={"event": "llm_client_retry"},
                )
                continue
            if response.status_code != 200:
                raise ModelCallError(f"llm provider 返回 {response.status_code}")
            data = response.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            result = LLMCallResult(
                content=content, usage=data.get("usage"), messages=messages
            )
            if schema is not None:
                try:
                    result.parsed = schema.model_validate(_extract_json_object(content))
                except ValidationError as exc:
                    raise LLMStructureError(f"模型输出未通过 schema 校验：{exc}") from exc
            if trace_id and trace_name:
                langfuse_tracing.trace_generation(
                    trace_id, trace_name, provider.model_name, messages,
                    content, result.usage, metadata=trace_metadata,
                )
            return result
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(f"llm 调用超时（{timeout_seconds}s）") from exc
        except httpx.HTTPError as exc:
            if attempt == 1:
                last_error = exc
                continue
            raise ModelCallError(f"llm 调用网络错误：{exc}") from exc
    raise ModelCallError(f"llm 调用失败：{last_error}")
