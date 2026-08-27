"""提示词注入检测（防护样例）：命中文本留痕（traceId），并在日志中告警。

防护是双层的：
1. 检测层（本模块）：正则命中常见注入模式，记日志留痕；
2. 约束层（rag.build_rag_prompt）：召回文本包裹分隔符并在系统提示中声明其为数据。
"""
import logging
import re

logger = logging.getLogger(__name__)

PATTERNS = [
    re.compile(r"忽略(之前|以上|上述|所有)(的)?(指令|指示|提示)", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"(输出|打印|泄露|显示)(你的|系统|system)?\s*(系统)?\s*(提示词|prompt)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
]


def scan(text: str) -> list[str]:
    """返回命中的注入模式描述列表（不返回原文，避免日志泄露文档正文）。"""
    hits = []
    for idx, pattern in enumerate(PATTERNS):
        if pattern.search(text):
            hits.append(f"pattern_{idx}")
    return hits


def scan_chunks(contents: list[str]) -> int:
    """扫描召回块，命中时告警留痕，返回命中块数。"""
    hit_count = 0
    for content in contents:
        hits = scan(content)
        if hits:
            hit_count += 1
            logger.warning(
                "prompt injection pattern detected in retrieved chunk",
                extra={"event": "injection_detected", "extra": {"patterns": hits}},
            )
    return hit_count
