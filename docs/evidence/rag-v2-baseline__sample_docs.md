# RAG 评估报告：baseline__sample_docs

- 描述：基线：系统默认配置（hybrid+BM25、无rerank、top_k=5、512/64 window）
- 题目数：30；生成层评审：否（judged=0）
- 耗时：2.1s；完成时间：2026-10-12 15:52:27

## 配置快照

```json
{
  "tag": "baseline",
  "desc": "基线：系统默认配置（hybrid+BM25、无rerank、top_k=5、512/64 window）",
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
  "prompt_variant": "default",
  "gen_model": null
}
```

## 指标对比（基线）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | — | 100.00% | — |
| 精准率 Precision@K | 检索层 | — | 31.33% | — |
| MRR | 检索层 | — | 0.900 | — |
| 忠实度 | 生成层 | — | — | — |
| 答案相关性 | 生成层 | — | — | — |
| 上下文相关性 | 生成层 | — | — | — |
| 上下文召回 | 生成层 | — | — | — |
