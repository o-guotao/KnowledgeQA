# RAG 评估报告：iter02-nohybrid

- 描述：检索参数：关闭混合检索（消融，仅向量）
- 题目数：50；生成层评审：是（judged=50）
- 耗时：180.6s；完成时间：2026-10-12 16:32:48

## 配置快照

```json
{
  "tag": "iter02-nohybrid",
  "desc": "检索参数：关闭混合检索（消融，仅向量）",
  "top_k": 5,
  "top_k_mode": "fixed",
  "candidate_multiplier": 4,
  "hybrid": false,
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

- `hybrid`: True → False

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 96.00% | -4.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 24.80% | -1.20% |
| MRR | 检索层 | 0.942 | 0.852 | -0.090 |
| 忠实度 | 生成层 | 97.31% | 96.78% | -0.53% |
| 答案相关性 | 生成层 | 95.80% | 92.60% | -3.20% |
| 上下文相关性 | 生成层 | 26.00% | 25.60% | -0.40% |
| 上下文召回 | 生成层 | 99.50% | 94.83% | -4.67% |

## 逐题命中变化

- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=False rank=0
- q26 退费从申请审核到钱到账，一共大概要多久？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q27 客户投诉闹大了，多久之内要给出书面处理报告？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q33 会议室单次最长可以预订多久？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q37 自助取数的查询结果保留多久？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q39 订阅的每日报表几点前会推送？：基线 hit=True rank=2 → 本轮 hit=True rank=3
- q42 备用金借款的上限和核销时限分别是多少？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=False rank=0
- q45 请梳理一笔报销从提交到打款的完整流程和时限。：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=False rank=0
- q26 退费从申请审核到钱到账，一共大概要多久？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q27 客户投诉闹大了，多久之内要给出书面处理报告？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q33 会议室单次最长可以预订多久？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q37 自助取数的查询结果保留多久？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q39 订阅的每日报表几点前会推送？：基线 hit=True rank=2 → 本轮 hit=True rank=3
- q42 备用金借款的上限和核销时限分别是多少？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=False rank=0
- q45 请梳理一笔报销从提交到打款的完整流程和时限。：基线 hit=True rank=1 → 本轮 hit=True rank=2

## 未命中题目

- q20（factual/easy）常规发布窗口是每周哪几天？
- q43（factual/easy）供应商的对外付款集中在每周几？
- q20（factual/easy）常规发布窗口是每周哪几天？
- q43（factual/easy）供应商的对外付款集中在每周几？
