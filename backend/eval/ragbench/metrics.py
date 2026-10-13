"""检索层指标：Recall@K / Precision@K / MRR（chunk 级 gold）。

gold chunk 判定（与切分参数无关的运行时解析）：
    chunk 所属文档 ∈ gold_docs 且 chunk 内容含任一 gold_keyword（忽略空白差异）
semantic 策略下用 snippet（子块原文）判定，避免父块内容放大命中范围。
"""
from __future__ import annotations

import re


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def is_gold(document_name: str, chunk_text: str, gold_docs: list[str], gold_keywords: list[str]) -> bool:
    if document_name not in gold_docs:
        return False
    text = _norm(chunk_text)
    return any(_norm(kw) in text for kw in gold_keywords)


def retrieval_metrics(
    retrieved: list[tuple[str, str]],  # [(document_name, chunk_text)] 按排名序
    gold_docs: list[str],
    gold_keywords: list[str],
) -> dict:
    """单题检索指标。k 取实际返回条数。"""
    flags = [is_gold(doc, text, gold_docs, gold_keywords) for doc, text in retrieved]
    k = len(flags)
    first_rank = next((i + 1 for i, f in enumerate(flags) if f), 0)
    return {
        "k": k,
        "gold_hits": sum(flags),
        "hit": first_rank > 0,
        "first_rank": first_rank,
        "precision": round(sum(flags) / k, 4) if k else 0.0,
        "rr": round(1.0 / first_rank, 4) if first_rank else 0.0,
        "flags": flags,
    }


def aggregate_retrieval(items: list[dict]) -> dict:
    """跨题聚合：recall=命中率均值，precision=逐题精准率均值，mrr=RR 均值。"""
    n = len(items)
    if not n:
        return {"recall_at_k": 0.0, "precision_at_k": 0.0, "mrr": 0.0}
    return {
        "recall_at_k": round(sum(1 for it in items if it["hit"]) / n, 4),
        "precision_at_k": round(sum(it["precision"] for it in items) / n, 4),
        "mrr": round(sum(it["rr"] for it in items) / n, 4),
    }
