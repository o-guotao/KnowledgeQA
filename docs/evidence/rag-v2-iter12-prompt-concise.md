# RAG 评估报告：iter12-prompt-concise

- 描述：生成参数：prompt 默认→简洁变体（120字约束）
- 题目数：50；生成层评审：是（judged=50）
- 耗时：154.6s；完成时间：2026-10-12 16:59:24

## 配置快照

```json
{
  "tag": "iter12-prompt-concise",
  "desc": "生成参数：prompt 默认→简洁变体（120字约束）",
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
  "context_chunks": 5,
  "prompt_variant": "concise",
  "gen_model": null
}
```

## 与基线的变量差异（应为单变量）

- `prompt_variant`: default → concise

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 26.00% | +0.00% |
| MRR | 检索层 | 0.942 | 0.942 | +0.000 |
| 忠实度 | 生成层 | 97.31% | 98.10% | +0.79% |
| 答案相关性 | 生成层 | 95.80% | 95.20% | -0.60% |
| 上下文相关性 | 生成层 | 26.00% | 24.80% | -1.20% |
| 上下文召回 | 生成层 | 99.50% | 99.50% | +0.00% |

## 逐题命中变化

（无变化）
