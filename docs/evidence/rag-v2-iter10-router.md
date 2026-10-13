# RAG 评估报告：iter10-router

- 描述：查询处理：固定 top_k → L4 LLM Router（需 API key）
- 题目数：50；生成层评审：是（judged=50）
- 耗时：216.3s；完成时间：2026-10-12 16:54:02

## 配置快照

```json
{
  "tag": "iter10-router",
  "desc": "查询处理：固定 top_k → L4 LLM Router（需 API key）",
  "top_k": 5,
  "top_k_mode": "router",
  "candidate_multiplier": 4,
  "hybrid": true,
  "bm25": true,
  "rrf_k": 60,
  "rerank": false,
  "chunk_size": 512,
  "chunk_overlap": 64,
  "chunk_strategy": "window",
  "context_chunks": 5,
  "prompt_variant": "default",
  "gen_model": null
}
```

## 与基线的变量差异（应为单变量）

- `top_k_mode`: fixed → router

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 35.55% | +9.55% |
| MRR | 检索层 | 0.942 | 0.910 | -0.032 |
| 忠实度 | 生成层 | 97.31% | 98.71% | +1.40% |
| 答案相关性 | 生成层 | 95.80% | 95.80% | +0.00% |
| 上下文相关性 | 生成层 | 26.00% | 37.46% | +11.46% |
| 上下文召回 | 生成层 | 99.50% | 99.50% | +0.00% |

## 逐题命中变化

- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=True rank=3
- q26 退费从申请审核到钱到账，一共大概要多久？：基线 hit=True rank=1 → 本轮 hit=True rank=3
- q37 自助取数的查询结果保留多久？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q42 备用金借款的上限和核销时限分别是多少？：基线 hit=True rank=1 → 本轮 hit=True rank=2
