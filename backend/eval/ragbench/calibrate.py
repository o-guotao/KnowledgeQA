"""judge 校准辅助：导出已评审题目的答案与四项指标明细，供人工抽检。

用法：python -m eval.ragbench.calibrate [--tag baseline]
输出：results/<tag>/calibration_review.md
"""
import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="baseline")
    args = parser.parse_args()

    items_file = BASE_DIR / "results" / args.tag / "items.jsonl"
    items = [json.loads(line) for line in items_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    judged = [it for it in items if it.get("judge")]
    # 去重：同 id 保留最后一条（断点续跑可能重复）
    dedup = {it["id"]: it for it in judged}

    lines = ["# judge 校准抽检明细", ""]
    for it in dedup.values():
        j = it["judge"]
        lines.append(f"## {it['id']} {it['q']}")
        lines.append(f"- 答案：{it.get('answer', '')[:200]}")
        lines.append(
            f"- 指标：忠实度={j['faithfulness']} 答案相关性={j['answer_relevance']} "
            f"上下文相关性={j['context_relevance']} 上下文召回={j['context_recall']}"
        )
        d = j.get("details", {})
        fr = d.get("faithfulness", {})
        if fr.get("claims"):
            lines.append(f"- 忠实度论断（{fr.get('supported')}/{fr.get('total')} 支持）：")
            for c in fr["claims"]:
                lines.append(f"  - {c}")
        ar = d.get("answer_relevance", {})
        if ar.get("reason"):
            lines.append(f"- 相关性理由：{ar['reason']}")
        cr = d.get("context_recall", {})
        if cr.get("total"):
            lines.append(f"- 上下文召回覆盖：{cr.get('covered')}/{cr.get('total')}")
        lines.append("")

    out = items_file.parent / "calibration_review.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 {len(dedup)} 题评审明细 -> {out}")


if __name__ == "__main__":
    main()
