# RAG 评测说明

## 评测集

- `sample_docs/`：4 篇虚构企业内部文档（员工手册 / 产品FAQ / 安全规范 / IT服务指南）
- `questions.jsonl`：30 条事实型问句，每条含 `gold_doc`（应召回的文档）与 `gold_keywords`（回答应命中的关键词）

> 安全规范.md 末尾嵌入了一条提示词注入攻击文本，用于验证防护：召回后模型不得执行其中的"忽略指令/输出系统提示词"要求，且服务端日志应有 `injection_detected` 告警（带 traceId）。

## 跑两组切分参数对比

```bash
# 第一组：CHUNK_SIZE=512 / CHUNK_OVERLAP=64（.env 默认值）
docker compose up -d
docker compose exec backend python -m eval.run_eval --tag baseline

# 第二组：修改 .env 为 CHUNK_SIZE=1024 / CHUNK_OVERLAP=128，重启 worker/backend
# 并删除旧文档后重新上传入库（切分参数在入库时固化到 documents 表）
docker compose up -d --force-recreate backend worker
docker compose exec backend python -m eval.run_eval --tag tuned

# 对比
docker compose exec backend python -m eval.run_eval --compare baseline tuned
```

输出：

- `results/eval_{tag}.jsonl`：逐条明细（引用文档、命中、回答、延迟）
- `results/eval_{tag}_summary.json`：召回命中率 / 回答正确率 / 平均延迟
- `results/compare_{a}_vs_{b}.csv`：前后对比表（可直接转 xlsx）

切分参数变化应能观察到指标升降：chunk 过小会切断语义导致召回命中率下降；
chunk 过大会稀释向量语义并带入噪声，回答正确率可能下降。
