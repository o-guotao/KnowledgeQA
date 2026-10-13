# RAG 评估报告：iter08-semantic

- 描述：切分策略：window→semantic 父子块
- 题目数：50；生成层评审：是（judged=50）
- 耗时：168.0s；完成时间：2026-10-12 16:47:12

## 配置快照

```json
{
  "tag": "iter08-semantic",
  "desc": "切分策略：window→semantic 父子块",
  "top_k": 5,
  "top_k_mode": "fixed",
  "candidate_multiplier": 4,
  "hybrid": true,
  "bm25": true,
  "rrf_k": 60,
  "rerank": false,
  "chunk_size": 512,
  "chunk_overlap": 64,
  "chunk_strategy": "semantic",
  "context_chunks": 5,
  "prompt_variant": "default",
  "gen_model": null
}
```

## 与基线的变量差异（应为单变量）

- `chunk_strategy`: window → semantic

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 24.00% | -2.00% |
| MRR | 检索层 | 0.942 | 0.967 | +0.025 |
| 忠实度 | 生成层 | 97.31% | 98.82% | +1.51% |
| 答案相关性 | 生成层 | 95.80% | 94.60% | -1.20% |
| 上下文相关性 | 生成层 | 26.00% | 24.80% | -1.20% |
| 上下文召回 | 生成层 | 99.50% | 98.50% | -1.00% |

## 逐题命中变化

- q06 采购验收合格后，财务多久完成付款？：基线 hit=True rank=2 → 本轮 hit=True rank=1
- q13 公司每月几号发工资？：基线 hit=True rank=1 → 本轮 hit=True rank=3
- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=True rank=1
- q32 朋友来公司找我，可以直接进到办公区吗？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q39 订阅的每日报表几点前会推送？：基线 hit=True rank=2 → 本轮 hit=True rank=1
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=True rank=1
- q06 采购验收合格后，财务多久完成付款？：基线 hit=True rank=2 → 本轮 hit=True rank=1
- q13 公司每月几号发工资？：基线 hit=True rank=1 → 本轮 hit=True rank=3
- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=True rank=1
- q32 朋友来公司找我，可以直接进到办公区吗？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q39 订阅的每日报表几点前会推送？：基线 hit=True rank=2 → 本轮 hit=True rank=1
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=True rank=1
