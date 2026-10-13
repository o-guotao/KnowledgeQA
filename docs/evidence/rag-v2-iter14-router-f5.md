# RAG 评估报告：iter14-router-f5

- 描述：自定义：['top_k_mode=router', 'router_factual=5']
- 题目数：50；生成层评审：是（judged=50）
- 耗时：206.7s；完成时间：2026-10-12 17:43:36

## 配置快照

```json
{
  "tag": "iter14-router-f5",
  "desc": "自定义：['top_k_mode=router', 'router_factual=5']",
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
  "gen_model": null,
  "router_factual": 5,
  "router_list": null,
  "router_comparison": null,
  "router_summary": null
}
```

## 与基线的变量差异（应为单变量）

- `top_k_mode`: fixed → router
- `router_factual`: None → 5

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 22.75% | -3.25% |
| MRR | 检索层 | 0.942 | 0.942 | +0.000 |
| 忠实度 | 生成层 | 97.31% | 97.91% | +0.60% |
| 答案相关性 | 生成层 | 95.80% | 97.60% | +1.80% |
| 上下文相关性 | 生成层 | 26.00% | 26.00% | +0.00% |
| 上下文召回 | 生成层 | 99.50% | 99.50% | +0.00% |

## 逐题命中变化

（无变化）
