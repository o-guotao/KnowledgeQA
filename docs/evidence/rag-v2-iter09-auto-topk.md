# RAG 评估报告：iter09-auto-topk

- 描述：查询处理：固定 top_k → L2 启发式 auto_top_k
- 题目数：50；生成层评审：是（judged=50）
- 耗时：176.3s；完成时间：2026-10-12 16:50:08

## 配置快照

```json
{
  "tag": "iter09-auto-topk",
  "desc": "查询处理：固定 top_k → L2 启发式 auto_top_k",
  "top_k": 5,
  "top_k_mode": "auto",
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

- `top_k_mode`: fixed → auto

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 27.20% | +1.20% |
| MRR | 检索层 | 0.942 | 0.942 | +0.000 |
| 忠实度 | 生成层 | 97.31% | 97.57% | +0.26% |
| 答案相关性 | 生成层 | 95.80% | 97.00% | +1.20% |
| 上下文相关性 | 生成层 | 26.00% | 29.87% | +3.87% |
| 上下文召回 | 生成层 | 99.50% | 99.50% | +0.00% |

## 逐题命中变化

（无变化）
