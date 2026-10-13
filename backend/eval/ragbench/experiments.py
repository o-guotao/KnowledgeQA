"""实验矩阵与 CLI 入口。

用法（backend/ 目录下）：
    python -m eval.ragbench.experiments --list                      # 查看实验矩阵
    python -m eval.ragbench.experiments --only baseline             # 仅基线（检索层）
    python -m eval.ragbench.experiments --only baseline --with-llm  # 基线（含生成层评审）
    python -m eval.ragbench.experiments --all --with-llm            # 全部单变量迭代
    python -m eval.ragbench.experiments --custom mytag --set rerank=true --set top_k=8
    附加参数：--force 重跑 / --sample N 只跑前 N 题（调试用） / --questions 指定评估集
"""
import argparse
import asyncio
import dataclasses
import os
import sys

# ---- 离线环境 bootstrap（须在 import app 之前设置）----
os.environ.setdefault("DB_BACKEND", "sqlite")
os.environ.setdefault("DATABASE_URL", "sqlite:///./eval_ragbench_global.db")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("EMBEDDING_BACKEND", "fastembed")
os.environ.setdefault("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
os.environ.setdefault("EMBEDDING_DIM", "512")
os.environ.setdefault("ENVIRONMENT", "development")

# Windows GBK 控制台：统一 UTF-8 输出，避免特殊符号/中文打印异常
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

from pathlib import Path  # noqa: E402

from eval.ragbench.config import ExperimentConfig  # noqa: E402
from eval.ragbench.runner import load_questions, run_experiment  # noqa: E402
from eval.ragbench import report  # noqa: E402

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = BASE_DIR / "dataset" / "questions_v2.jsonl"

# 基线 = 系统当前默认配置（hybrid+BM25 开、rerank 关、top_k=5 固定、chunk 512/64 window）
BASELINE = ExperimentConfig(tag="baseline", desc="基线：系统默认配置（hybrid+BM25、无rerank、top_k=5、512/64 window）")

# 单变量实验矩阵：每轮仅与基线相差一个变量（分四类，按序执行）
EXPERIMENTS: list[ExperimentConfig] = [
    # —— 检索参数 ——
    dataclasses.replace(BASELINE, tag="iter01-topk10", desc="检索参数：top_k 5→10", top_k=10),
    dataclasses.replace(BASELINE, tag="iter02-nohybrid", desc="检索参数：关闭混合检索（消融，仅向量）", hybrid=False),
    dataclasses.replace(BASELINE, tag="iter03-rerank", desc="检索参数：开启 rerank（候选池 top_k×4）", rerank=True),
    dataclasses.replace(BASELINE, tag="iter04-rrf-k30", desc="检索参数：RRF k 60→30（monkey-patch）", rrf_k=30),
    # —— 索引/切分参数 ——
    dataclasses.replace(BASELINE, tag="iter05-chunk256", desc="切分参数：chunk_size 512→256", chunk_size=256),
    dataclasses.replace(BASELINE, tag="iter06-chunk1024", desc="切分参数：chunk_size 512→1024", chunk_size=1024),
    dataclasses.replace(BASELINE, tag="iter07-overlap128", desc="切分参数：overlap 64→128", chunk_overlap=128),
    dataclasses.replace(BASELINE, tag="iter08-semantic", desc="切分策略：window→semantic 父子块", chunk_strategy="semantic"),
    # —— 查询处理 ——
    dataclasses.replace(BASELINE, tag="iter09-auto-topk", desc="查询处理：固定 top_k → L2 启发式 auto_top_k", top_k_mode="auto"),
    dataclasses.replace(BASELINE, tag="iter10-router", desc="查询处理：固定 top_k → L4 LLM Router（需 API key）", top_k_mode="router"),
    # —— 生成参数（需 --with-llm）——
    dataclasses.replace(BASELINE, tag="iter11-context3", desc="生成参数：注入上下文块数 5→3", context_chunks=3),
    dataclasses.replace(BASELINE, tag="iter12-prompt-concise", desc="生成参数：prompt 默认→简洁变体（120字约束）", prompt_variant="concise"),
]

ALL_TAGS = ["baseline"] + [e.tag for e in EXPERIMENTS]


def _parse_set(pairs: list[str]) -> dict:
    """--set key=value 解析，值做 bool/int 类型推断。"""
    overrides: dict = {}
    valid = set(ExperimentConfig.__dataclass_fields__) - {"tag", "desc"}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set 格式应为 key=value：{pair}")
        k, v = pair.split("=", 1)
        if k not in valid:
            raise SystemExit(f"未知配置字段 {k!r}，可选：{sorted(valid)}")
        if v.lower() in ("true", "false"):
            overrides[k] = v.lower() == "true"
        else:
            try:
                overrides[k] = int(v)
            except ValueError:
                overrides[k] = v
    return overrides


async def main() -> None:
    parser = argparse.ArgumentParser(prog="ragbench")
    parser.add_argument("--list", action="store_true", help="列出实验矩阵")
    parser.add_argument("--only", help="只跑指定 tag")
    parser.add_argument("--tags", help="逗号分隔的多个 tag（按序执行）")
    parser.add_argument("--all", action="store_true", help="跑全部实验")
    parser.add_argument("--custom", help="自定义实验 tag（配合 --set）")
    parser.add_argument("--set", nargs="*", default=[], help="自定义覆盖 key=value")
    parser.add_argument("--with-llm", action="store_true", help="跑生成层（需 DEEPSEEK_API_KEY）")
    parser.add_argument("--force", action="store_true", help="归档旧结果重跑")
    parser.add_argument("--sample", type=int, help="只跑前 N 题（调试）")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS), help="评估集 jsonl 路径")
    parser.add_argument("--corpus", default="dataset/corpus", help="语料目录（相对 backend/eval/ 或绝对路径）")
    args = parser.parse_args()

    if args.list:
        print(f"{'tag':<24}{'变更'}")
        print("-" * 70)
        for e in [BASELINE, *EXPERIMENTS]:
            print(f"{e.tag:<24}{e.desc}")
        return

    corpus_dir = Path(args.corpus)
    if not corpus_dir.is_absolute():
        corpus_dir = BASE_DIR / corpus_dir
    if not corpus_dir.is_dir():
        raise SystemExit(f"语料目录不存在：{corpus_dir}")

    questions_path = Path(args.questions)
    if not questions_path.is_absolute() and not questions_path.exists():
        questions_path = BASE_DIR / questions_path  # 相对 backend/eval/ 解析
    questions = load_questions(questions_path)
    print(f"[eval] {len(questions)} questions from {questions_path}（语料：{corpus_dir.name}）")

    runs: list[ExperimentConfig] = []
    if args.custom:
        runs.append(dataclasses.replace(
            BASELINE, tag=args.custom, desc=f"自定义：{args.set}", **_parse_set(args.set)
        ))
    elif args.only or args.tags:
        wanted = [t.strip() for t in (args.tags or args.only).split(",") if t.strip()]
        runs = [e for t in wanted for e in [BASELINE, *EXPERIMENTS] if e.tag == t]
        if len(runs) != len(wanted):
            missing = set(wanted) - {e.tag for e in runs}
            raise SystemExit(f"未知 tag {missing}，用 --list 查看")
    elif args.all:
        runs = [BASELINE, *EXPERIMENTS]
    else:
        parser.print_help()
        return

    from eval.ragbench.runner import DEFAULT_CORPUS_DIR

    done_tags: list[str] = []
    for cfg in runs:
        run_tag = cfg.tag if corpus_dir == DEFAULT_CORPUS_DIR else f"{cfg.tag}__{corpus_dir.name}"
        await run_experiment(cfg, questions, with_llm=args.with_llm,
                             force=args.force, sample=args.sample, corpus_dir=corpus_dir)
        baseline_tag = "baseline" if corpus_dir == DEFAULT_CORPUS_DIR else f"baseline__{corpus_dir.name}"
        out = report.write_run_report(run_tag, baseline_tag=baseline_tag)
        print(f"[report] {out}")
        done_tags.append(run_tag)

    if len(done_tags) > 1:
        tags = [t for t in ALL_TAGS if t in set(done_tags)]
        md, xlsx = report.write_final_summary(tags)
        print(f"[summary] {md}\n[summary] {xlsx}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
