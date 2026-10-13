"""评估集构建：校验种子问句并生成 questions_v2.jsonl。

校验规则（纯 stdlib，不依赖 app）：
- gold_docs 必须存在于 dataset/corpus/
- 每个 gold_keyword 必须能在至少一篇 gold_doc 中找到（忽略空白差异）
- reference_answer 非空且长度在 [10, 600]；关键词覆盖率低于 50% 时告警
- type ∈ {factual,list,comparison,summary}；difficulty ∈ {easy,hard}
- 难例（hard）占比须 ≥ 40%，否则报错

用法：
    python -m eval.gen_dataset            # 校验 + 落盘 dataset/questions_v2.jsonl
    python -m eval.gen_dataset --llm      # 先用 DeepSeek 重新生成参考答案再校验（需 DEEPSEEK_API_KEY）
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
CORPUS_DIR = DATASET_DIR / "corpus"
SEED_FILE = DATASET_DIR / "questions_seed.jsonl"
OUT_FILE = DATASET_DIR / "questions_v2.jsonl"

TYPES = {"factual", "list", "comparison", "summary"}
DIFFICULTIES = {"easy", "hard"}
HARD_RATIO_MIN = 0.40


def _norm(s: str) -> str:
    """忽略空白差异的匹配归一化。"""
    return re.sub(r"\s+", "", s)


def load_corpus() -> dict[str, str]:
    docs: dict[str, str] = {}
    for path in sorted(CORPUS_DIR.iterdir()):
        if path.suffix.lower() in (".md", ".txt"):
            docs[path.name] = path.read_text(encoding="utf-8")
    return docs


def load_seed() -> list[dict]:
    items = []
    for lineno, line in enumerate(SEED_FILE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"种子文件第 {lineno} 行不是合法 JSON：{exc}")
    return items


def _read_root_env() -> dict[str, str]:
    """读项目根 .env（backend/eval -> 上两级 = 项目根），仅在 --llm 模式下使用。"""
    env_file = Path(__file__).resolve().parents[2] / ".env"
    out: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


async def gen_reference_answer(item: dict, corpus: dict[str, str], cfg: dict[str, str]) -> str:
    """--llm 模式：基于 gold 文档原文用 DeepSeek 生成参考答案。"""
    import httpx

    api_key = os.environ.get("DEEPSEEK_API_KEY") or cfg.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise SystemExit("--llm 模式需要 DEEPSEEK_API_KEY（环境变量或根 .env）")
    base_url = os.environ.get("DEEPSEEK_BASE_URL") or cfg.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL") or cfg.get("DEEPSEEK_MODEL", "deepseek-chat")

    gold_text = "\n\n".join(f"【{name}】\n{corpus[name]}" for name in item["gold_docs"])
    prompt = (
        "基于以下资料，为给定问题撰写一段简洁、准确的参考答案（100 字以内，只依据资料，不要编造）：\n\n"
        f"{gold_text}\n\n问题：{item['q']}\n\n参考答案："
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 300,
                "stream": False,
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek 返回 {resp.status_code}: {resp.text[:200]}")
    return (resp.json()["choices"][0]["message"]["content"] or "").strip()


def validate(items: list[dict], corpus: dict[str, str]) -> tuple[list[dict], list[str]]:
    """校验并补充 id 字段。返回 (合法条目, 告警列表)；致命错误直接 SystemExit。"""
    warnings: list[str] = []
    corpus_norm = {name: _norm(text) for name, text in corpus.items()}
    valid: list[dict] = []
    for i, item in enumerate(items, 1):
        qid = f"q{i:02d}"
        q = item.get("q", "").strip()
        gold_docs = item.get("gold_docs") or []
        keywords = item.get("gold_keywords") or []
        ref = (item.get("reference_answer") or "").strip()
        qtype = item.get("type")
        difficulty = item.get("difficulty")

        if not q:
            raise SystemExit(f"{qid}: 缺少 q")
        if not gold_docs:
            raise SystemExit(f"{qid}: 缺少 gold_docs — {q[:30]}")
        for name in gold_docs:
            if name not in corpus:
                raise SystemExit(f"{qid}: gold_doc 不存在于语料库：{name}")
        if not keywords:
            raise SystemExit(f"{qid}: 缺少 gold_keywords — {q[:30]}")
        for kw in keywords:
            if not any(_norm(kw) in corpus_norm[name] for name in gold_docs):
                raise SystemExit(f"{qid}: 关键词 {kw!r} 在 gold_docs {gold_docs} 中均未出现 — {q[:30]}")
        if not (10 <= len(ref) <= 600):
            raise SystemExit(f"{qid}: reference_answer 长度 {len(ref)} 越界 [10,600] — {q[:30]}")
        if qtype not in TYPES:
            raise SystemExit(f"{qid}: 非法 type {qtype!r}")
        if difficulty not in DIFFICULTIES:
            raise SystemExit(f"{qid}: 非法 difficulty {difficulty!r}")

        ref_norm = _norm(ref)
        covered = sum(1 for kw in keywords if _norm(kw) in ref_norm)
        if covered / len(keywords) < 0.5:
            warnings.append(f"{qid}: 参考答案关键词覆盖率 {covered}/{len(keywords)} 偏低 — {q[:30]}")

        valid.append({
            "id": qid,
            "q": q,
            "gold_docs": gold_docs,
            "gold_keywords": keywords,
            "reference_answer": ref,
            "type": qtype,
            "difficulty": difficulty,
        })

    hard = sum(1 for it in valid if it["difficulty"] == "hard")
    ratio = hard / len(valid) if valid else 0.0
    if ratio < HARD_RATIO_MIN:
        raise SystemExit(f"难例占比 {ratio:.0%}（{hard}/{len(valid)}）低于 {HARD_RATIO_MIN:.0%} 要求")
    return valid, warnings


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="用 DeepSeek 重新生成参考答案")
    args = parser.parse_args()

    corpus = load_corpus()
    if not corpus:
        raise SystemExit(f"语料库为空：{CORPUS_DIR}")
    items = load_seed()
    print(f"[dataset] 语料 {len(corpus)} 篇，种子问句 {len(items)} 条")

    if args.llm:
        cfg = _read_root_env()
        for i, item in enumerate(items, 1):
            item["reference_answer"] = await gen_reference_answer(item, corpus, cfg)
            print(f"  [llm {i:02d}/{len(items)}] {item['q'][:30]}")

    valid, warnings = validate(items, corpus)
    OUT_FILE.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in valid) + "\n",
        encoding="utf-8",
    )

    by_type: dict[str, int] = {}
    for it in valid:
        by_type[it["type"]] = by_type.get(it["type"], 0) + 1
    hard = sum(1 for it in valid if it["difficulty"] == "hard")
    multi_doc = sum(1 for it in valid if len(it["gold_docs"]) > 1)
    print(f"[dataset] 已生成 {OUT_FILE}（{len(valid)} 条）")
    print(f"[dataset] 题型分布：{by_type}；难例 {hard}/{len(valid)}（{hard / len(valid):.0%}）；多文档题 {multi_doc}")
    for w in warnings:
        print(f"[warn] {w}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
