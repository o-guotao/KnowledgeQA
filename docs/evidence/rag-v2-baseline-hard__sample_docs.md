# RAG 评估报告：baseline-hard__sample_docs

- 描述：自定义：[]
- 题目数：10；生成层评审：否（judged=0）
- 耗时：1.2s；完成时间：2026-10-12 15:52:29

## 配置快照

```json
{
  "tag": "baseline-hard",
  "desc": "自定义：[]",
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

## 与基线的变量差异（应为单变量）


## 指标对比（基线 baseline__sample_docs vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 31.33% | 24.00% | -7.33% |
| MRR | 检索层 | 0.900 | 0.800 | -0.100 |
| 忠实度 | 生成层 | — | — | — |
| 答案相关性 | 生成层 | — | — | — |
| 上下文相关性 | 生成层 | — | — | — |
| 上下文召回 | 生成层 | — | — | — |

## 逐题命中变化

- q02 出差住酒店一晚上最多能报多少钱？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q05 早上忘记打卡了会不会扣钱？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q06 在家办公一周能有几天？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q09 星图导数据一次最多能导多少行？：基线 hit=True rank=1 → 本轮 hit=True rank=2
