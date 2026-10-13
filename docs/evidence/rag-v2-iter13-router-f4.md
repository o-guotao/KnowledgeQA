# RAG 评估报告：iter13-router-f4

- 描述：自定义：['top_k_mode=router', 'router_factual=4']
- 题目数：50；生成层评审：是（judged=50）
- 耗时：209.8s；完成时间：2026-10-12 17:39:46

## 配置快照

```json
{
  "tag": "iter13-router-f4",
  "desc": "自定义：['top_k_mode=router', 'router_factual=4']",
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
  "router_factual": 4,
  "router_list": null,
  "router_comparison": null,
  "router_summary": null
}
```

## 与基线的变量差异（应为单变量）

- `top_k_mode`: fixed → router
- `router_factual`: None → 4

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 27.55% | +1.55% |
| MRR | 检索层 | 0.942 | 0.942 | +0.000 |
| 忠实度 | 生成层 | 97.31% | 97.45% | +0.14% |
| 答案相关性 | 生成层 | 95.80% | 95.80% | +0.00% |
| 上下文相关性 | 生成层 | 26.00% | 29.20% | +3.20% |
| 上下文召回 | 生成层 | 99.50% | 99.50% | +0.00% |

## 逐题命中变化

（无变化）
