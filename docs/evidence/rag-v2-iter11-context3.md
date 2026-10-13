# RAG 评估报告：iter11-context3

- 描述：生成参数：注入上下文块数 5→3
- 题目数：50；生成层评审：是（judged=50）
- 耗时：167.2s；完成时间：2026-10-12 16:56:49

## 配置快照

```json
{
  "tag": "iter11-context3",
  "desc": "生成参数：注入上下文块数 5→3",
  "top_k": 5,
  "top_k_mode": "fixed",
  "candidate_multiplier": 4,
  "hybrid": true,
  "bm25": true,
  "rrf_k": 60,
  "rerank": false,
  "chunk_size": 512,
  "chunk_overlap": 64,
  "chunk_strategy": "window",
  "context_chunks": 3,
  "prompt_variant": "default",
  "gen_model": null
}
```

## 与基线的变量差异（应为单变量）

- `context_chunks`: 5 → 3

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 26.00% | +0.00% |
| MRR | 检索层 | 0.942 | 0.942 | +0.000 |
| 忠实度 | 生成层 | 97.31% | 98.42% | +1.11% |
| 答案相关性 | 生成层 | 95.80% | 93.20% | -2.60% |
| 上下文相关性 | 生成层 | 26.00% | 40.00% | +14.00% |
| 上下文召回 | 生成层 | 99.50% | 96.83% | -2.67% |

## 逐题命中变化

（无变化）
