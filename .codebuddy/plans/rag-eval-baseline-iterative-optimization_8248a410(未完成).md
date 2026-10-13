---
name: rag-eval-baseline-iterative-optimization
overview: 构建全新 RAG 评估集（问句+gold文档+参考答案），实现检索层（召回率/精准率/MRR）与生成层（忠实度/答案相关性/上下文相关性/上下文召回）七项指标的脚本式评估流水线，建立基线后按"每次只改一个变量"的原则逐轮优化并输出对比报告，后续沉淀到 Eval Center。
todos:
  - id: build-dataset
    content: 用 [subagent:code-explorer] 确认可配置入口后，构建全新评估集：新语料 + questions_v2.jsonl（含参考答案），gen_dataset.py 生成并落盘
    status: pending
  - id: retrieval-metrics
    content: 实现 ragbench 运行器与检索层指标：Recall@K、Precision@K、MRR（config/metrics/runner）
    status: pending
    dependencies:
      - build-dataset
  - id: generation-judge
    content: 实现生成层 judge 模块：忠实度、答案相关性、上下文相关性、上下文召回（复用 llm_client，DeepSeek 评审）
    status: pending
    dependencies:
      - build-dataset
  - id: baseline-run
    content: 定义基线配置并跑通首轮评估，确认 .env LLM Key 后输出基线报告（Markdown + 逐题明细）
    status: pending
    dependencies:
      - retrieval-metrics
      - generation-judge
  - id: single-var-iterations
    content: 按单变量原则依次迭代：检索参数→索引切分→查询处理→生成参数，每轮输出 delta 对比报告
    status: pending
    dependencies:
      - baseline-run
  - id: summary-report
    content: 用 [skill:xlsx] 生成全迭代 7 指标汇总表与最终结论报告（docs/evidence/）
    status: pending
    dependencies:
      - single-var-iterations
  - id: eval-center-integration
    content: 沉淀到 Eval Center：eval_runner 接入新指标与新评估集，前端 EvalCenterTab 增加指标列与对比图表
    status: pending
    dependencies:
      - summary-report
---

## 用户需求

针对「内知 · KnowledgeQA」RAG 系统，建立一套完整的评估与迭代优化体系：先全新构建评估集，再建立基线，然后围绕 7 项指标按"每次只改一个变量"的原则依次优化，并输出每轮评估结果。

## 产品概述

本项目是企业内部知识问答系统（FastAPI + pgvector + BM25 混合检索 + cross-encoder 重排 + DeepSeek 生成）。本次工作不改变线上问答行为，而是新增一套离线评估流水线：构建带参考答案的评估集 → 基线评估 → 单变量迭代优化 → 输出对比报告，最终沉淀到管理端 Eval Center。

## 核心功能

- **全新评估集构建**：从零构建评估集（问句 + gold 文档 + gold chunk + 参考答案 reference answer），jsonl 落盘；参考答案支撑"上下文召回"指标
- **检索层指标**：召回率 Recall@K、精准率 Precision@K、MRR
- **生成层指标（RAGAS 风格，DeepSeek 作 judge）**：忠实度、答案相关性、上下文相关性、上下文召回
- **基线评估**：以当前默认配置为基线（单向量召回、默认 top_k/chunk 参数、现有 prompt），输出 7 项指标基线报告
- **单变量迭代优化**：每轮实验仅修改一个变量（检索参数 / 索引切分 / 查询处理 / 生成参数四类），输出与基线及上一轮的分项指标对比
- **结果输出**：每轮生成 Markdown 对比报告 + 汇总对比表（xlsx），评估集与报告均落盘
- **Eval Center 沉淀**：将新指标与新评估集接入管理端 Eval Center，支持页面触发与图表查看

## 技术栈

- Python 3.11+ / FastAPI 生态（沿用后端现有依赖：SQLAlchemy asyncio、httpx、openpyxl）
- 离线评估环境复用现有模式：SQLite + fastembed（BGE-small-zh-v1.5）建库，无需启动完整后端（参照 `backend/eval/run_recall_eval.py`）
- 生成与评审：DeepSeek API，复用 `backend/app/services/llm_client.py` 统一客户端
- 报告：Markdown（docs/evidence/）+ openpyxl 生成 xlsx 对比表（参照 `backend/eval/make_eval_xlsx.py`）

## 实现方案

### 总体策略

不引入 ragas 第三方库（仓库当前无此依赖，且指标口径需与自研 recall/MRR 对齐），**自研轻量 RAGAS 风格 judge 模块**：忠实度（答案拆分为论断，逐条判定是否被上下文支持，取支持比例）、答案相关性（LLM 反向生成问题与原始问句 embedding 余弦相似度）、上下文相关性（LLM 判定各 chunk 与问句的相关比例）、上下文召回（参考答案拆分为论断，判定是否被召回上下文覆盖）。这样指标口径透明、可复现、无新依赖。

### 关键决策

- **评估集全新构建**：新语料库（沿用 7 篇 sample_docs 风格并扩充干扰文档）+ 40~50 条问句，每条含 `question / gold_doc / gold_chunk_id(可选) / gold_keywords / reference_answer / type(factual|list|comparison|summary)`。参考答案先用 DeepSeek 基于 gold 文档生成，再人工规则校验（关键词覆盖、长度），落盘 `backend/eval/dataset/questions_v2.jsonl`
- **精准率定义**：Precision@K = top_k 中属于 gold_doc 的 chunk 数 / k（多 gold_doc 时按命中任一计）；与现有 recall_hit、MRR 共用同一趟检索结果计算，零额外开销
- **单变量实验框架**：基线配置 dataclass（含全部可调变量字段：top_k、candidate_multiplier、rrf_k、hybrid 权重、rerank 开关/截断、chunk_size/overlap/strategy、query_rewrite、router 模式、prompt 模板、context chunk 数、生成模型），每轮实验 = 基线 + 单字段覆盖，配置快照随结果存档，保证可复现
- **检索层评估离线跑**（SQLite + fastembed，同 run_recall_eval 模式）；**生成层按需跑**（`--with-llm`，每轮仅对生成参数变更的实验跑全部 40+ 条，其余轮次可抽样复用，控制 API 成本与时间）
- **结果对比**：每轮输出 `基线 vs 本轮` 的 7 指标 delta 表；最终输出全迭代汇总表（xlsx）+ 结论报告

### 性能与成本

- 检索层单轮：40+ 条 × 单趟 retrieve，秒级；bge-reranker 加载为单例，跨实验复用
- 生成层单轮：40+ 条 ×（1 次生成 + 4 项 judge，judge 内部论断级判定合并为 2~3 次 LLM 调用/题），约 200 次 LLM 调用/轮，需串行限速 + 失败重试 + 结果落盘断点续跑
- BM25 索引按 chunk 指纹懒重建（复用现有 `_ensure_index` 机制），切分参数变更轮次自动重建

## 架构

```mermaid
flowchart LR
    DS[评估集 dataset/<br>questions_v2.jsonl + corpus] --> RUN[ragbench runner<br>基线配置 + 单变量覆盖]
    RUN --> KB[建库<br>SQLite+fastembed]
    KB --> RET[retrieve 检索]
    RET --> RM[检索层指标<br>Recall@K / Precision@K / MRR]
    RET --> GEN[DeepSeek 生成答案]
    GEN --> JD[judge 评审<br>忠实度/答案相关性<br>上下文相关性/上下文召回]
    RM --> RPT[report<br>Markdown + xlsx 对比报告]
    JD --> RPT
    RPT -.沉淀.-> EC[Eval Center<br>eval_runner + 前端图表]
```

## 目录结构

```
backend/eval/
├── dataset/
│   ├── questions_v2.jsonl       # [NEW] 全新评估集：question/gold_doc/gold_keywords/reference_answer/type
│   ├── corpus/                  # [NEW] 新语料文档（md，含干扰文档）
│   └── README.md                # [NEW] 评估集构建说明与人工校验记录
├── gen_dataset.py               # [NEW] 评估集生成脚本：LLM 生成参考答案 + 关键词覆盖校验 + 落盘
├── ragbench/
│   ├── __init__.py              # [NEW]
│   ├── config.py                # [NEW] BaselineConfig dataclass + 单变量实验矩阵定义
│   ├── metrics.py               # [NEW] 检索层指标：recall_at_k / precision_at_k / mrr
│   ├── judge.py                 # [NEW] 生成层 RAGAS 风格指标（复用 services/llm_client.py，DeepSeek 评审）
│   ├── runner.py                # [NEW] 评估运行器：建库→检索→（可选）生成→指标→逐题明细落盘（断点续跑）
│   ├── report.py                # [NEW] 对比报告生成：Markdown delta 表 + 汇总 xlsx
│   └── experiments.py           # [NEW] 实验序列定义：每轮单变量覆盖 + 执行入口 CLI
docs/evidence/
├── rag-baseline-基线报告.md      # [NEW] 基线 7 指标报告
├── rag-iter-NN-*.md             # [NEW] 每轮单变量迭代对比报告
└── RAG评估汇总表.xlsx            # [NEW] 全迭代 7 指标汇总对比表
backend/app/services/eval_runner.py  # [MODIFY] 沉淀阶段：新增 precision 指标与生成层指标接入配置组
backend/app/api/admin_eval.py        # [MODIFY] 沉淀阶段：数据集上传/指标字段透传
frontend/src/pages/admin/EvalCenterTab.tsx  # [MODIFY] 沉淀阶段：新指标列与对比图表
backend/eval/README.md               # [MODIFY] 补充 ragbench 使用说明
```

## 实施要点

- 遵循 Trellis 工作流：写码前阅读 `.trellis/spec/backend/` 对应层规范与 `backend/eval/README.md`
- runner 复用 `run_recall_eval.py` 的环境初始化模式（import app 前设置 env：SQLite/fastembed/`get_settings.cache_clear()`）
- judge 输出强制 JSON 结构 + 解析失败重试（≤2 次）+ 单题失败不中断整轮；LLM 调用串行限速，日志只记摘要不落答案全文
- 每轮实验配置快照 + 逐题明细 jsonl 落盘 `backend/eval/results/<run_tag>/`，保证可复现与断点续跑
- Windows + PowerShell 环境：命令示例用 `python -m eval.ragbench.experiments`；管道输出用 `Out-String`
- 执行生成层评估前需确认 `.env` 中 DeepSeek API Key 已配置；检索层轮次不依赖 LLM

## Agent Extensions

### Skill

- **xlsx**
- Purpose: 生成全迭代 7 指标汇总对比表（docs/evidence/RAG评估汇总表.xlsx），含基线与各轮 delta、条件格式
- Expected outcome: 产出可读性强的汇总工作簿，与现有 RAG评测对比表.xlsx 风格一致

### SubAgent

- **code-explorer**
- Purpose: 深度确认 rag.py retrieve 参数化能力、chunking/rerank/query_rewrite/router 的可配置入口，确保单变量实验的覆盖点真实可配
- Expected outcome: 给出每个实验变量的确切配置入口（env 变量/函数参数），避免实验定义与代码脱节