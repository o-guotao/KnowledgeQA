"""多轮对话的检索 query 条件改写（conversational retrieval）。

问题：追问句（"结构类型呢"）脱离历史无语义，直接检索会召回无关片段。
方案：最近几轮历史 + 新问题交给 LLM 做【条件改写】——
仅当问题依赖历史（省略主语/指代）时改写为独立完整问题；
问题自足或话题已切换时原样返回，避免历史污染新话题的检索。

任何一步失败都回退原始问题（由调用方 catch），绝不影响主流程。
"""
import json
import logging
from dataclasses import dataclass, field

import httpx

from app.services.deepseek import ModelCallError
from app.services.model_configs import ProviderConfig

logger = logging.getLogger(__name__)

# 改写只看最近几轮：足够消解指代，又控制 token 成本与久远话题的干扰
_HISTORY_TURNS = 3
# 单条历史消息截断长度：assistant 回答可能很长，改写只需话题上下文
_TURN_CHAR_LIMIT = 500
# 改写独立超时上限：串行在检索前，不能让它吃光 TTFT 预算
_TIMEOUT_SECONDS = 30.0

_SYSTEM_PROMPT = (
    "你是检索查询改写器。根据对话历史，判断用户的【新问题】是否依赖历史才能被检索系统理解。\n"
    "规则：\n"
    "1. 仅当新问题省略了主语/对象或含有指代（如“它”“这个”“那”“呢”“还有吗”），"
    "才结合历史把它改写成一个独立、完整、包含关键实体的问题。\n"
    "2. 若新问题本身完整自足，或与历史话题无关（话题已切换），必须原样返回，禁止融入任何历史信息。\n"
    "3. 只输出一行 JSON，不要输出任何解释或其他文字：\n"
    '{"rewritten": true/false, "query": "最终用于检索的问题"}'
)


@dataclass
class RewriteResult:
    query: str  # 最终用于检索的 query（未改写时为原文）
    rewritten: bool
    usage: dict | None = None  # 改写调用的 token usage（供计费）
    messages: list[dict] = field(default_factory=list)  # 改写调用入参（供 tracing）
    output: str = ""  # 模型原始输出（供 tracing）


def _build_messages(history: list[dict], question: str) -> list[dict]:
    turns = history[-_HISTORY_TURNS * 2 :]
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for m in turns:
        messages.append({"role": m["role"], "content": m["content"][:_TURN_CHAR_LIMIT]})
    messages.append({"role": "user", "content": f"【新问题】{question}"})
    return messages


def _parse_output(raw: str, question: str) -> tuple[str, bool]:
    """解析模型 JSON 输出；格式非法/未改写/空 query 一律回退原文。"""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return question, False
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return question, False
    query = data.get("query")
    if not data.get("rewritten") or not isinstance(query, str) or not query.strip():
        return question, False
    return query.strip(), True


async def rewrite_query(
    provider: ProviderConfig, history: list[dict], question: str
) -> RewriteResult:
    """条件改写检索 query。history 为不含当前问题的历史消息；失败抛异常由调用方兜底。"""
    messages = _build_messages(history, question)
    timeout = httpx.Timeout(min(provider.timeout_seconds, _TIMEOUT_SECONDS), connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{provider.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {provider.api_key}"},
            json={
                "model": provider.model_name,
                "messages": messages,
                "stream": False,
                "temperature": 0,  # 改写要确定性，不用对话的采样参数
                "max_tokens": 200,
            },
        )
    if response.status_code != 200:
        raise ModelCallError(f"query rewrite provider {response.status_code}")
    data = response.json()
    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    query, rewritten = _parse_output(raw, question)
    return RewriteResult(
        query=query, rewritten=rewritten,
        usage=data.get("usage"), messages=messages, output=raw,
    )
