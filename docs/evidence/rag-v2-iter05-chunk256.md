# RAG 评估报告：iter05-chunk256

- 描述：切分参数：chunk_size 512→256
- 题目数：50；生成层评审：是（judged=50）
- 耗时：168.3s；完成时间：2026-10-12 16:38:42

## 配置快照

```json
{
  "tag": "iter05-chunk256",
  "desc": "切分参数：chunk_size 512→256",
  "top_k": 5,
  "top_k_mode": "fixed",
  "candidate_multiplier": 4,
  "hybrid": true,
  "bm25": true,
  "rrf_k": 60,
  "rerank": false,
  "chunk_size": 256,
  "chunk_overlap": 64,
  "chunk_strategy": "window",
  "context_chunks": 5,
  "prompt_variant": "default",
  "gen_model": null
}
```

## 与基线的变量差异（应为单变量）

- `chunk_size`: 512 → 256

## 指标对比（基线 baseline vs 本轮）

| 指标 | 层 | 基线 | 本轮 | delta |
|---|---|---|---|---|
| 召回率 Recall@K | 检索层 | 100.00% | 100.00% | +0.00% |
| 精准率 Precision@K | 检索层 | 26.00% | 32.00% | +6.00% |
| MRR | 检索层 | 0.942 | 0.930 | -0.012 |
| 忠实度 | 生成层 | 97.31% | 96.88% | -0.43% |
| 答案相关性 | 生成层 | 95.80% | 95.80% | +0.00% |
| 上下文相关性 | 生成层 | 26.00% | 34.40% | +8.40% |
| 上下文召回 | 生成层 | 99.50% | 99.50% | +0.00% |

## 逐题命中变化

- q13 公司每月几号发工资？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=True rank=1
- q21 半夜收到一级告警，多久内必须响应？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=True rank=4
- q13 公司每月几号发工资？：基线 hit=True rank=1 → 本轮 hit=True rank=4
- q20 常规发布窗口是每周哪几天？：基线 hit=True rank=4 → 本轮 hit=True rank=1
- q21 半夜收到一级告警，多久内必须响应？：基线 hit=True rank=1 → 本轮 hit=True rank=2
- q43 供应商的对外付款集中在每周几？：基线 hit=True rank=3 → 本轮 hit=True rank=4
