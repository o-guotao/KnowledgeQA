# RAG 评估报告：best-combo

- 描述：自定义：['chunk_overlap=128', 'top_k_mode=auto']
- 题目数：50；生成层评审：是（judged=50）
- 耗时：167.5s；完成时间：2026-10-12 17:12:11

## 配置快照

```json
{
  "tag": "best-combo",
  "desc": "自定义：['chunk_overlap=128', 'top_k_mode=auto']",
  "top_k": 5,
  "top_k_mode": "auto",
  "candidate_multiplier": 4,
  "hybrid": true,
  "bm25": true,
  "rrf_k": 60,
  "rerank": false,
  "chunk_size": 512,
  "chunk_overlap": 128,
  "chunk_strategy": "window",
  "context_chunks": 5,
  "prompt_variant": "default",
  "gen_model": null
}
```

## 与基线的变量差异（应为单变量）

- `top_k_mode`: fixed → auto
- `chunk_overlap`: 64 → 128

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 31.53% | +5.53% |
| MRR | 检索层 | 0.942 | 0.955 | +0.013 |
| 忠实度 | 生成层 | 97.31% | 97.87% | +0.56% |
| 答案相关性 | 生成层 | 95.80% | 97.00% | +1.20% |
| 上下文相关性 | 生成层 | 26.00% | 32.93% | +6.93% |
| 上下文召回 | 生成层 | 99.50% | 99.50% | +0.00% |

## 逐题命中变化

- q04 新供应商入库的资质审核需要多长时间？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q06 采购验收合格后，财务多久完成付款？：基线 hit=True rank=2 → 本轮 hit=True rank=1
- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=True rank=1
- q41 报销单提交后，财务多久完成审核？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=True rank=4
- q46 采购验收后的付款时限和员工报销的审核时限分别是多少？：基线 hit=True rank=2 → 本轮 hit=True rank=1
