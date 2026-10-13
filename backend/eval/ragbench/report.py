"""对比报告：每轮 Markdown delta 报告 + 全迭代汇总（Markdown + xlsx）。"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"
EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "docs" / "evidence"

RETRIEVAL_KEYS = ("recall_at_k", "precision_at_k", "mrr")
GENERATION_KEYS = ("faithfulness", "answer_relevance", "context_relevance", "context_recall")
METRIC_LABELS = {
    "recall_at_k": "召回率 Recall@K",
    "precision_at_k": "精准率 Precision@K",
    "mrr": "MRR",
    "faithfulness": "忠实度",
    "answer_relevance": "答案相关性",
    "context_relevance": "上下文相关性",
    "context_recall": "上下文召回",
}


def load_summary(tag: str) -> dict | None:
    f = RESULTS_DIR / tag / "summary.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def load_config(tag: str) -> dict | None:
    f = RESULTS_DIR / tag / "config.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def load_items(tag: str) -> list[dict]:
    f = RESULTS_DIR / tag / "items.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fmt(v, pct: bool = True) -> str:
    if v is None:
        return "—"
    return f"{v:.2%}" if pct else f"{v:.3f}"


def _delta(cur, base, pct: bool = True) -> str:
    if cur is None or base is None:
        return "—"
    d = cur - base
    return f"{d:+.2%}" if pct else f"{d:+.3f}"


def _metric(summary: dict, key: str):
    if key in RETRIEVAL_KEYS:
        return summary.get("retrieval", {}).get(key)
    return summary.get("generation", {}).get(key)


def write_run_report(tag: str, baseline_tag: str = "baseline") -> Path:
    """单轮报告：基线 vs 本轮 7 指标 delta + 配置差异 + 逐题波动。"""
    summary = load_summary(tag)
    config = load_config(tag)
    if summary is None or config is None:
        raise SystemExit(f"缺少 {tag} 的 summary/config，无法生成报告")
    base = load_summary(baseline_tag) if tag != baseline_tag else None

    lines = [
        f"# RAG 评估报告：{tag}",
        "",
        f"- 描述：{summary.get('desc', '')}",
        f"- 题目数：{summary['total']}；生成层评审：{'是' if summary.get('generation') else '否'}"
        f"（judged={summary.get('generation', {}).get('judged', 0)}）",
        f"- 耗时：{summary.get('elapsed_s')}s；完成时间：{summary.get('finished_at')}",
        "",
        "## 配置快照",
        "",
        "```json",
        json.dumps(config, ensure_ascii=False, indent=2),
        "```",
        "",
    ]

    if base and tag != baseline_tag:
        base_cfg = load_config(baseline_tag) or {}
        diffs = {k: (base_cfg.get(k), config.get(k)) for k in config
                 if base_cfg.get(k) != config.get(k) and k not in ("tag", "desc")}
        lines += ["## 与基线的变量差异（应为单变量）", ""]
        for k, (a, b) in diffs.items():
            lines.append(f"- `{k}`: {a} → {b}")
        lines.append("")

    lines += [
        "## 指标对比" + (f"（基线 {baseline_tag} vs 本轮）" if base else "（基线）"),
        "",
        "| 指标 | 层 | 基线 | 本轮 | delta |",
        "|---|---|---|---|---|",
    ]
    for key in RETRIEVAL_KEYS:
        cur = _metric(summary, key)
        b = _metric(base, key) if base else None
        pct = key != "mrr"
        lines.append(
            f"| {METRIC_LABELS[key]} | 检索层 | {_fmt(b, pct)} | {_fmt(cur, pct)} | {_delta(cur, b, pct)} |"
        )
    for key in GENERATION_KEYS:
        cur = _metric(summary, key)
        b = _metric(base, key) if base else None
        lines.append(
            f"| {METRIC_LABELS[key]} | 生成层 | {_fmt(b)} | {_fmt(cur)} | {_delta(cur, b)} |"
        )
    lines.append("")

    # 逐题波动（与基线相比命中状态变化的题）
    if base:
        base_items = {it["id"]: it for it in load_items(baseline_tag)}
        cur_items = load_items(tag)
        changes = []
        for it in cur_items:
            b_it = base_items.get(it["id"])
            if not b_it:
                continue
            if (it["hit"], it["first_rank"]) != (b_it["hit"], b_it["first_rank"]):
                changes.append(
                    f"- {it['id']} {it['q'][:40]}：基线 hit={b_it['hit']} rank={b_it['first_rank']}"
                    f" → 本轮 hit={it['hit']} rank={it['first_rank']}"
                )
        lines += ["## 逐题命中变化", ""] + (changes or ["（无变化）"]) + [""]

    fails = [it for it in load_items(tag) if not it["hit"]]
    if fails:
        lines += ["## 未命中题目", ""]
        for it in fails:
            lines.append(f"- {it['id']}（{it['type']}/{it['difficulty']}）{it['q']}")
        lines.append("")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE_DIR / f"rag-v2-{tag}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_final_summary(tags: list[str], out_name: str = "RAG评估汇总表v2") -> tuple[Path, Path]:
    """全迭代汇总：Markdown 总表 + xlsx 对比表（含基线与各轮 delta）。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    runs = [s for t in tags if (s := load_summary(t))]
    if not runs:
        raise SystemExit("没有任何已完成的实验结果")
    base = runs[0] if runs[0]["tag"] == "baseline" else None

    all_keys = RETRIEVAL_KEYS + GENERATION_KEYS
    header = ["实验", "变更说明"] + [METRIC_LABELS[k] for k in all_keys] + ["judged", "耗时s"]

    md = ["# RAG 评估全迭代汇总", "",
          "| 实验 | 变更说明 | " + " | ".join(METRIC_LABELS[k] for k in all_keys) + " |",
          "|---|---|" + "---|" * len(all_keys)]
    for s in runs:
        cells = []
        for k in all_keys:
            v = _metric(s, k)
            pct = k != "mrr"
            cell = _fmt(v, pct)
            if base and s["tag"] != "baseline":
                bv = _metric(base, k)
                if v is not None and bv is not None:
                    cell += f"（{v - bv:+.2%}）" if pct else cell + f"（{v - bv:+.3f}）"
            cells.append(cell)
        md.append(f"| {s['tag']} | {s.get('desc', '')} | " + " | ".join(cells) + " |")
    md.append("")

    wb = Workbook()
    ws = wb.active
    ws.title = "全迭代汇总"
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
    for s in runs:
        row = [s["tag"], s.get("desc", "")]
        for k in all_keys:
            v = _metric(s, k)
            row.append(round(v, 4) if v is not None else "—")
        row.append(s.get("generation", {}).get("judged", 0))
        row.append(s.get("elapsed_s"))
        ws.append(row)
    # 各指标列最优值加粗（第 3 列起）
    for col in range(3, 3 + len(all_keys)):
        values = [
            (r, ws.cell(row=r, column=col).value)
            for r in range(2, ws.max_row + 1)
            if isinstance(ws.cell(row=r, column=col).value, (int, float))
        ]
        if values:
            best_row, _ = max(values, key=lambda x: x[1])
            ws.cell(row=best_row, column=col).font = Font(bold=True)
    for col_letter, width in zip("ABCDEFGHIJKL", (22, 44, 12, 14, 9, 10, 12, 13, 12, 8, 8)):
        ws.column_dimensions[col_letter].width = width

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    md_path = EVIDENCE_DIR / f"rag-v2-汇总.md"
    xlsx_path = EVIDENCE_DIR / f"{out_name}.xlsx"
    md_path.write_text("\n".join(md), encoding="utf-8")
    wb.save(xlsx_path)
    return md_path, xlsx_path
