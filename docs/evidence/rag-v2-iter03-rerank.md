# RAG 评估报告：iter03-rerank

- 描述：检索参数：开启 rerank（候选池 top_k×4）
- 题目数：50；生成层评审：否（judged=0）
- 耗时：372.5s；完成时间：2026-10-12 15:36:49

## 配置快照

```json
{
  "tag": "iter03-rerank",
  "desc": "检索参数：开启 rerank（候选池 top_k×4）",
  "top_k": 5,
  "top_k_mode": "fixed",
  "candidate_multiplier": 4,
  "hybrid": true,
  "bm25": true,
  "rrf_k": 60,
  "rerank": true,
  "chunk_size": 512,
  "chunk_overlap": 64,
  "chunk_strategy": "window",
  "context_chunks": 5,
  "prompt_variant": "default",
  "gen_model": null
}
```

## 与基线的变量差异（应为单变量）

- `rerank`: False → True

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 25.60% | -0.40% |
| MRR | 检索层 | 0.942 | 0.945 | +0.003 |
| 忠实度 | 生成层 | — | — | — |
| 答案相关性 | 生成层 | — | — | — |
| 上下文相关性 | 生成层 | — | — | — |
| 上下文召回 | 生成层 | — | — | — |

## 逐题命中变化

- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=True rank=2
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=True rank=4
