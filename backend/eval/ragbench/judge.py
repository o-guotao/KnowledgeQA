"""生成层指标（RAGAS 风格自研 judge，DeepSeek 评审，不引第三方库）。

四项指标：
- faithfulness 忠实度：答案拆论断 → 逐条判定是否被召回上下文支持，取支持比例
- answer_relevance 答案相关性：LLM 按评分细则直接打 0~1 分（简化掉反向生成+余弦链路）
- context_relevance 上下文相关性：逐块判定与问题的相关比例
- context_recall 上下文召回：参考答案拆论断 → 判定被召回上下文覆盖的比例

可靠性约定：全部 JSON 结构化输出（json_mode + Pydantic 校验）；解析失败重试 1 次；
单项最终失败返回 None（该题该项不计入均值），不中断整轮。
"""
from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from app.services.llm_client import LLMStructureError, chat
from app.services.model_configs import ProviderConfig

logger = logging.getLogger(__name__)

# 全局并发闸门：评审调用串行限速，避免触发 provider 限流
_sem = asyncio.Semaphore(3)


class _Claims(BaseModel):
    claims: list[str]


class _Verdict(BaseModel):
    claim: str
    supported: bool


class _Verdicts(BaseModel):
    verdicts: list[_Verdict]


class _Relevance(BaseModel):
    relevant: list[bool]


class _Coverage(BaseModel):
    claim: str
    covered: bool


class _Coverages(BaseModel):
    claims: list[_Coverage]


class _Score(BaseModel):
    score: float
    reason: str = ""


def _fmt_contexts(contexts: list[str]) -> str:
    return "\n\n".join(f"【资料 {i}】\n{c}" for i, c in enumerate(contexts, 1))


async def _call_json(provider: ProviderConfig, schema, system: str, user: str, max_tokens: int):
    """JSON 结构化调用 + 解析失败重试 1 次；最终失败返回 None。"""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in (1, 2):
        try:
            async with _sem:
                result = await chat(
                    provider, messages, schema=schema, json_mode=True,
                    max_tokens=max_tokens, temperature=0, timeout_cap=60.0,
                )
            return result.parsed
        except LLMStructureError:
            if attempt == 2:
                logger.warning("judge 结构化输出两次解析失败，放弃本项")
                return None
        except Exception as exc:  # ModelCallError/Timeout 等：不重试（chat 内部已重试 5xx）
            logger.warning("judge 调用失败：%s", exc)
            return None
    return None


async def faithfulness(provider: ProviderConfig, question: str, answer: str, contexts: list[str]) -> tuple[float | None, dict]:
    """忠实度 = 被上下文支持的论断数 / 论断总数（无论断记 1.0）。"""
    claims_obj = await _call_json(
        provider, _Claims,
        "你是事实抽取器。把回答拆分为原子论断（最小事实陈述），忽略客套话与引用标记。"
        '只输出 JSON：{"claims": ["论断1", ...]}',
        f"【回答】\n{answer}",
        500,
    )
    if claims_obj is None:
        return None, {"error": "claims_extract_failed"}
    if not claims_obj.claims:
        return 1.0, {"claims": []}
    verdicts_obj = await _call_json(
        provider, _Verdicts,
        "你是事实核查员。逐条判断每个论断是否能被给定资料支持（资料明确陈述或直接蕴含即为支持）。"
        '只输出 JSON：{"verdicts": [{"claim": "原论断", "supported": true|false}, ...]}，顺序与输入一致。',
        f"{_fmt_contexts(contexts)}\n\n【待核查论断】\n" + "\n".join(f"{i}. {c}" for i, c in enumerate(claims_obj.claims, 1)),
        800,
    )
    if verdicts_obj is None or not verdicts_obj.verdicts:
        return None, {"error": "verify_failed", "claims": claims_obj.claims}
    supported = sum(1 for v in verdicts_obj.verdicts if v.supported)
    total = len(verdicts_obj.verdicts)
    return round(supported / total, 4), {
        "claims": claims_obj.claims,
        "supported": supported,
        "total": total,
    }


async def answer_relevance(provider: ProviderConfig, question: str, answer: str) -> tuple[float | None, dict]:
    """答案相关性：LLM 按细则直接 0~1 评分。"""
    obj = await _call_json(
        provider, _Score,
        "你是答案质量评审。只评估回答与问题的匹配程度，按细则打分（0~1，保留两位小数）：\n"
        "1.0=直接完整回答了问题；0.7=回答了但夹带与问题无关的内容或轻微偏题；\n"
        "0.4=只回答了问题的一半或明显答非所问；0.1=基本未回答问题；0=完全无关或拒答。\n"
        "评分规则：\n"
        "- 不得因回答未包含资料之外的信息（如行业惯例、法规背景、国家标准）而扣分；\n"
        "- 回答中补充的、与问题相关的资料内信息不算冗余，不扣分；\n"
        "- 只有夹带与问题无关的内容时才按 0.7 档扣分。\n"
        '只输出 JSON：{"score": 0.0, "reason": "一句话依据"}',
        f"【问题】{question}\n\n【回答】\n{answer}",
        200,
    )
    if obj is None:
        return None, {"error": "score_failed"}
    score = max(0.0, min(1.0, obj.score))
    return round(score, 4), {"reason": obj.reason}


async def context_relevance(provider: ProviderConfig, question: str, contexts: list[str]) -> tuple[float | None, dict]:
    """上下文相关性 = 与问题相关的块数 / 总块数。"""
    if not contexts:
        return 0.0, {"relevant": []}
    obj = await _call_json(
        provider, _Relevance,
        "你是检索质量评审。逐条判断每段资料是否有助于回答给定问题（包含答案或关键背景即为相关）。"
        '只输出 JSON：{"relevant": [true|false, ...]}，长度与资料段数一致、顺序一致。',
        f"【问题】{question}\n\n{_fmt_contexts(contexts)}",
        300,
    )
    if obj is None or len(obj.relevant) != len(contexts):
        return None, {"error": "judge_failed"}
    score = sum(obj.relevant) / len(obj.relevant)
    return round(score, 4), {"relevant": obj.relevant}


async def context_recall(provider: ProviderConfig, reference_answer: str, contexts: list[str]) -> tuple[float | None, dict]:
    """上下文召回 = 参考答案论断中被召回上下文覆盖的比例。"""
    obj = await _call_json(
        provider, _Coverages,
        "你是检索完备性评审。先把参考答案拆分为原子论断，再逐条判断该论断能否被给定资料支持。"
        '只输出 JSON：{"claims": [{"claim": "论断", "covered": true|false}, ...]}',
        f"{_fmt_contexts(contexts)}\n\n【参考答案】\n{reference_answer}",
        800,
    )
    if obj is None or not obj.claims:
        return None, {"error": "judge_failed"}
    covered = sum(1 for c in obj.claims if c.covered)
    return round(covered / len(obj.claims), 4), {
        "covered": covered,
        "total": len(obj.claims),
    }


async def judge_all(
    provider: ProviderConfig,
    question: str,
    answer: str,
    reference_answer: str,
    contexts: list[str],
) -> dict:
    """一题四项指标并发评审。返回 {metric: score|None, "details": {...}}。"""
    faith, rel, ctx_rel, ctx_rec = await asyncio.gather(
        faithfulness(provider, question, answer, contexts),
        answer_relevance(provider, question, answer),
        context_relevance(provider, question, contexts),
        context_recall(provider, reference_answer, contexts),
    )
    return {
        "faithfulness": faith[0],
        "answer_relevance": rel[0],
        "context_relevance": ctx_rel[0],
        "context_recall": ctx_rec[0],
        "details": {
            "faithfulness": faith[1],
            "answer_relevance": rel[1],
            "context_relevance": ctx_rel[1],
            "context_recall": ctx_rec[1],
        },
    }


def aggregate_generation(items: list[dict]) -> dict:
    """跨题聚合生成层指标（None 不计入均值）。"""
    out: dict[str, float | int | None] = {}
    judged = 0
    for key in ("faithfulness", "answer_relevance", "context_relevance", "context_recall"):
        values = [it["judge"][key] for it in items if it.get("judge") and it["judge"].get(key) is not None]
        out[key] = round(sum(values) / len(values), 4) if values else None
        judged = max(judged, len(values))
    out["judged"] = judged
    return out
