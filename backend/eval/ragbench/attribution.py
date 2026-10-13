"""MRR 归因分析：逐题对比两个 run 的检索明细，定位首命中排名变化的来源。

对比维度：top_k 变化（含 router 分类）、first_rank 变化、gold 命中变化；
按机制分类：
- 融合池偏移：分类正确（与题型一致或合理）但 k 缩小后 RRF 融合序改变致 gold 排名后移
- 排名提升：首命中排名前移（k 缩小挤出高位噪音）
- 分类存疑：Router 分类与人工题型标签明显不符
- 无变化：first_rank 不变

用法：python -m eval.ragbench.attribution [--base baseline] [--iter iter10-router]
输出：results/attribution_<base>_vs_<iter>.md + 控制台结论
"""
import argparse
import json
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

# Router 分类与人工题型的合理对应（factual→factual 等直译对应）
_TYPE_MAP = {"factual": "factual", "list": "list", "comparison": "comparison", "summary": "summary"}


def load_items(tag: str) -> dict[str, dict]:
    f = RESULTS_DIR / tag / "items.jsonl"
    items = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {it["id"]: it for it in items}  # 同 id 保留最后一条（续跑去重）


def router_category(top_k_src: str) -> str:
    """top_k_src 形如 'router:factual' / 'router:fallback' / 'fixed' / 'auto'。"""
    if top_k_src.startswith("router:"):
        return top_k_src.split(":", 1)[1]
    return top_k_src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="baseline")
    parser.add_argument("--iter", default="iter10-router")
    args = parser.parse_args()

    base = load_items(args.base)
    cur = load_items(args.iter)
    common = sorted(set(base) & set(cur))
    if not common:
        raise SystemExit("两个 run 没有共同题目")

    rows: list[dict] = []
    for qid in common:
        b, c = base[qid], cur[qid]
        cat = router_category(c.get("top_k_src", ""))
        expected = _TYPE_MAP.get(c.get("type"), c.get("type"))
        if b["first_rank"] == c["first_rank"]:
            mech = "无变化"
        elif c["first_rank"] > b["first_rank"]:
            mech = "分类存疑" if cat not in (expected, "fallback") else "融合池偏移"
        else:
            mech = "排名提升"
        rows.append({
            "id": qid, "q": c["q"], "type": c.get("type"), "cat": cat,
            "k_base": b["top_k"], "k_iter": c["top_k"],
            "rank_base": b["first_rank"], "rank_iter": c["first_rank"],
            "hit_base": b["hit"], "hit_iter": c["hit"], "mech": mech,
        })

    changed = [r for r in rows if r["mech"] != "无变化"]
    worse = [r for r in changed if r["rank_iter"] > r["rank_base"]]
    better = [r for r in changed if r["rank_iter"] < r["rank_base"]]
    rr_base = sum(1.0 / r["rank_base"] if r["rank_base"] else 0 for r in rows) / len(rows)
    rr_iter = sum(1.0 / r["rank_iter"] if r["rank_iter"] else 0 for r in rows) / len(rows)

    lines = [
        f"# MRR 归因：{args.base} vs {args.iter}",
        "",
        f"- 题目数 {len(rows)}；排名后移 {len(worse)} 题、前移 {len(better)} 题、不变 {len(rows) - len(changed)} 题",
        f"- 复算 MRR：{args.base}={rr_base:.4f} → {args.iter}={rr_iter:.4f}（Δ {rr_iter - rr_base:+.4f}）",
        "",
        "## 排名后移题目（损失来源）",
        "",
        "| 题 | 人工题型 | Router 分类 | k | rank 变化 | 机制 |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(worse, key=lambda x: x["rank_iter"] - x["rank_base"], reverse=True):
        lines.append(
            f"| {r['id']} {r['q'][:22]} | {r['type']} | {r['cat']} | {r['k_base']}→{r['k_iter']} "
            f"| {r['rank_base']}→{r['rank_iter']} | {r['mech']} |"
        )
    lines += ["", "## 排名前移题目（收益来源）", "",
              "| 题 | 人工题型 | Router 分类 | k | rank 变化 |", "|---|---|---|---|---|"]
    for r in better:
        lines.append(
            f"| {r['id']} {r['q'][:22]} | {r['type']} | {r['cat']} | {r['k_base']}→{r['k_iter']} "
            f"| {r['rank_base']}→{r['rank_iter']} |"
        )
    # 分类一致性统计
    mismatch = [r for r in rows if r["cat"] not in (_TYPE_MAP.get(r["type"]), "fallback", "fixed", "auto")]
    lines += ["", "## 分类一致性", "",
              f"- 与人工题型不一致：{len(mismatch)}/{len(rows)}"]
    for r in mismatch:
        lines.append(f"  - {r['id']}（{r['type']}→{r['cat']}）{r['q'][:30]} rank {r['rank_base']}→{r['rank_iter']}")
    lines.append("")

    out = RESULTS_DIR / f"attribution_{args.base}_vs_{args.iter}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"题目 {len(rows)}；后移 {len(worse)} / 前移 {len(better)} / 不变 {len(rows) - len(changed)}")
    print(f"复算 MRR：{rr_base:.4f} → {rr_iter:.4f}（Δ {rr_iter - rr_base:+.4f}）")
    by_mech: dict[str, int] = {}
    for r in worse:
        by_mech[r["mech"]] = by_mech.get(r["mech"], 0) + 1
    print(f"后移机制分布：{by_mech}；分类不一致 {len(mismatch)} 题")
    print(f"明细 -> {out}")


if __name__ == "__main__":
    main()
