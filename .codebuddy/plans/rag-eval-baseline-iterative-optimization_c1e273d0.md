---
name: rag-eval-baseline-iterative-optimization
overview: 构建高难度全新评估集（chunk 级 gold + 参考答案，难例≥40%），实现检索层（召回率/精准率/MRR）与生成层（忠实度/答案相关性/上下文相关性/上下文召回）七项指标的脚本式评估流水线，建立基线后按"每次只改一个变量"逐轮优化并输出对比报告与汇总表；Eval Center 沉淀移至第二期。
todos:
  - id: build-dataset
    content: 用 [subagent:code-explorer] 确认全部变量配置入口，构建新评估集（难例≥40%、chunk级gold、参考答案）并落盘
    status: completed
  - id: retrieval-metrics
    content: 实现 ragbench 运行器与检索层指标 Recall@K/Precision@K/MRR（config/metrics/runner）
    status: completed
    dependencies:
      - build-dataset
  - id: generation-judge
    content: 实现生成层 judge 四指标（复用 llm_client）并完成 10~20 题人工抽检校准
    status: completed
    dependencies:
      - build-dataset
  - id: baseline-run
    content: 定义基线配置，确认 .env LLM Key 后跑基线（新旧集交叉验证），输出基线报告
    status: completed
    dependencies:
      - retrieval-metrics
      - generation-judge
  - id: single-var-iterations
    content: 按单变量原则依次迭代：检索参数→索引切分→L2/L4 Router→生成参数，每轮输出 delta 报告
    status: completed
    dependencies:
      - baseline-run
  - id: summary-report
    content: 用 [skill:xlsx] 生成全迭代 7 指标汇总表与最终结论报告（docs/evidence/）
    status: completed
    dependencies:
      - single-var-iterations
---

## 用户需求

针对「内知 · KnowledgeQA」RAG 系统建立评估与迭代优化体系：全新构建评估集 → 建立基线 → 围绕 7 项指标按"每次评估只改一个变量"依次优化 → 输出每轮评估结果与汇总报告。

## 产品概述

企业知识问答系统（FastAPI + pgvector 向量 + BM25 关键词 RRF 混合检索 + cross-encoder 重排 + DeepSeek 生成）。本期新增离线评估流水线，不改变线上问答行为，不改动管理端 Eval Center（沉淀工作移出本期，作为后续独立任务）。

## 核心功能

- **全新评估集**：从零构建新语料 + 问句集（含 chunk 级 gold 标注、参考答案 reference_answer、题型标签），难例（同义改写/多文档聚合/对比型/强干扰）占比 ≥40%，jsonl 落盘；避免基线即饱和
- **检索层指标**：召回率 Recall@K、精准率 Precision@K、MRR（chunk 级 gold）
- **生成层指标**（RAGAS 风格自研，DeepSeek 作 judge，不引第三方库）：忠实度、答案相关性（LLM 直接 0~1 评分）、上下文相关性、上下文召回
- **judge 校准**：对 10~20 题人工抽检校准，逐题 judge 结果落盘可回溯
- **基线评估**：当前默认配置跑基线，新评估集 + 旧 30+10 题集交叉验证，输出 7 指标基线报告
- **单变量迭代**：每轮仅改一个变量（检索参数 / 索引切分 / 查询处理仅保留 L2 vs L4 Router / 生成参数），输出基线 vs 本轮 delta 对比；query 改写变量本期移除（单轮集上为空操作）
- **结果落盘**：每轮配置快照 + 逐题明细 jsonl + Markdown 报告 + 最终 xlsx 汇总表

## 技术栈

- Python 3.11+ / FastAPI 生态（沿用现有依赖：SQLAlchemy asyncio、httpx、openpyxl）
- 离线评估环境：SQLite + fastembed（BGE-small-zh-v1.5），复用 `backend/eval/run_recall_eval.py` 的环境初始化模式（import app 前置 env + `get_settings.cache_clear()`）
- 生成与评审：DeepSeek API，复用 `backend/app/services/llm_client.py` 统一客户端
- 报告：Markdown（docs/evidence/）+ openpyxl 生成 xlsx

## 实现方案

### 总体策略

已验证全部核心实验变量均可通过 **env 变量 + Settings 重载**注入（`backend/app/config.py` 中 `rag_top_k`、`rerank_candidate_multiplier`、`hybrid_search_enabled`、`bm25_enabled`、`rerank_enabled`、`chunk_size/chunk_overlap`、`llm_router_enabled` 均为 BaseSettings 字段），且 `backend/app/services/eval_runner.py`（第 44~87 行）已有成熟的"per-run env 覆盖"先例可复用——**不改 `rag.py` 本体**。少数硬编码变量（如 RRF k=60）用 monkey-patch 注入并随配置快照记录。

### 关键决策

- **指标口径**：Precision@K = top_k 中命中 gold chunk（或同属 gold_doc）的 chunk 数 / k；Recall/MRR 按 chunk 级 gold 计算；与现有自研口径对齐。生成层 4 指标自研轻量 judge：忠实度（拆论断→逐条判定上下文支持比例）、答案相关性（LLM 直接 0~1 评分，简化掉反向生成+embedding 余弦链路）、上下文相关性（LLM 判定各 chunk 与问句相关比例）、上下文召回（参考答案拆论断→判定被召回上下文覆盖比例）
- **单变量实验框架**：`ExperimentConfig` dataclass 覆盖全部可调字段；每轮实验 = 基线 + 单字段覆盖；配置快照 + 逐题明细落盘 `backend/eval/results/<run_tag>/`，支持断点续跑
- **成本模型**：生成层指标每轮全量重跑（检索变化即上下文变化，不可抽样复用）；基线 + 约 6~8 轮 × 每轮约 200 次 DeepSeek 调用，墙钟数小时；LLM 串行限速 + JSON 强制输出 + 解析失败重试 ≤2 次 + 单题失败不中断
- **交叉验证**：新评估集与旧 questions.jsonl/questions_hard.jsonl 同跑基线，保留历史可比性

### 性能与可靠性

- 检索层单轮秒级；reranker/embedding 模型单例跨实验复用；BM25 索引按指纹懒重建（切分参数变更轮自动重建）
- judge 日志只记摘要与分数不落答案全文；失败题目标记后整轮继续

## 架构

```mermaid
flowchart LR
    DS[评估集 dataset/<br>questions_v2.jsonl + corpus] --> RUN[ragbench runner<br>基线配置 + 单变量 env 覆盖]
    RUN --> KB[离线建库<br>SQLite + fastembed]
    KB --> RET[retrieve 检索]
    RET --> RM[检索层指标<br>Recall@K / Precision@K / MRR]
    RET --> GEN[DeepSeek 生成答案]
    GEN --> JD[judge 评审<br>忠实度/答案相关性<br>上下文相关性/上下文召回]
    JD --> CAL[人工抽检校准]
    RM --> RPT[report<br>Markdown delta + xlsx 汇总]
    JD --> RPT
```

## 目录结构

```
backend/eval/
├── dataset/
│   ├── questions_v2.jsonl       # [NEW] 新评估集：question/gold_doc/gold_chunk_id/gold_keywords/reference_answer/type/difficulty
│   ├── corpus/                  # [NEW] 新语料 md（含强干扰文档）
│   └── README.md                # [NEW] 评估集构建说明与人工校验记录
├── gen_dataset.py               # [NEW] 评估集生成：LLM 生成参考答案 + 关键词覆盖校验 + 落盘
├── ragbench/
│   ├── __init__.py              # [NEW]
│   ├── config.py                # [NEW] ExperimentConfig dataclass + 单变量实验矩阵（env 覆盖映射）
│   ├── metrics.py               # [NEW] 检索层指标：recall_at_k / precision_at_k / mrr（chunk 级 gold）
│   ├── judge.py                 # [NEW] 生成层 4 指标（复用 llm_client，DeepSeek 评审，JSON 输出+重试）
│   ├── runner.py                # [NEW] 运行器：env 覆盖→建库→检索→（可选）生成→指标→明细落盘+断点续跑
│   ├── report.py                # [NEW] 报告：Markdown delta 表 + 汇总 xlsx
│   └── experiments.py           # [NEW] 实验序列定义 + CLI 入口（python -m eval.ragbench.experiments）
├── results/<run_tag>/           # [NEW] 每轮配置快照 + 逐题明细 jsonl（gitignore）
└── README.md                    # [MODIFY] 补充 ragbench 使用说明
docs/evidence/
├── rag-v2-baseline-基线报告.md   # [NEW] 基线 7 指标报告（新集+旧集交叉验证）
├── rag-v2-iter-NN-*.md          # [NEW] 每轮单变量迭代对比报告
└── RAG评估汇总表v2.xlsx          # [NEW] 全迭代 7 指标汇总对比表
```

## 实施要点

- 写码前读 `.trellis/spec/backend/` 对应层规范与 `backend/eval/README.md`；遵循 Trellis 工作流
- env 覆盖模式复用 `eval_runner.py` 第 44~87 行先例；RRF k 等硬编码变量用 monkey-patch，不改 `rag.py`
- 生成层评估执行前确认 `.env` 中 DeepSeek Key 已配置；检索层轮次不依赖 LLM
- Windows + PowerShell：管道用 `Out-String` 不用 `cat`；pytest 回归现有 eval 脚本不受影响

## Agent Extensions

### SubAgent

- **code-explorer**
- Purpose: 确认 RRF k 值、rerank 截断阈值、prompt 模板等剩余变量的确切注入入口（env / 函数参数 / monkey-patch 点），输出实验变量→配置入口映射表
- Expected outcome: 实验矩阵中每个变量都有已验证的可配入口，无遗漏、不改线上代码

### Skill

- **xlsx**
- Purpose: 生成全迭代 7 指标汇总对比表（docs/evidence/RAG评估汇总表v2.xlsx），含基线与各轮 delta、条件格式
- Expected outcome: 风格与现有 RAG评测对比表.xlsx 一致的可读汇总工作簿