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

## ragbench：离线 RAG 评估流水线（评估集 v2）

7 项指标：检索层（召回率 Recall@K / 精准率 Precision@K / MRR，chunk 级 gold）+
生成层（忠实度 / 答案相关性 / 上下文相关性 / 上下文召回，DeepSeek 作 judge）。
每次实验只改一个变量，基线 = 系统默认配置（hybrid+BM25、无 rerank、top_k=5、512/64 window）。

```powershell
# 环境：conda langgraph（首次需 pip install -r requirements.txt，fastembed 用环境已有版本）
$env:PYTHONIOENCODING='utf-8'   # Windows 控制台必设

python -m eval.ragbench.experiments --list                      # 查看 12 个单变量实验
python -m eval.ragbench.experiments --only baseline             # 基线（仅检索层，秒级）
python -m eval.ragbench.experiments --only baseline --with-llm  # 基线（含生成层评审）
python -m eval.ragbench.experiments --all --with-llm            # 全部迭代
python -m eval.ragbench.experiments --custom mytag --set rerank=true --set top_k=8
python -m eval.ragbench.experiments --tags iter01-topk10,iter03-rerank --force
```

- 评估集：`dataset/questions_v2.jsonl`（50 题，构建与校验见 `dataset/README.md`）；
  `--questions` 可指定旧集做交叉验证（旧集无参考答案，自动跳过生成层评审）
- 知识库按切分三要素缓存于 `results/_kb/`，语料指纹不变则复用
- 断点续跑：已完成的题跳过；先跑检索层、后加 `--with-llm` 会自动补跑缺评审的题；
  同 tag 配置变更需 `--force`（自动归档旧明细）
- 结果：`results/<tag>/`（config.json / items.jsonl / summary.json）+
  `docs/evidence/rag-v2-<tag>.md` 单轮 delta 报告 + `rag-v2-汇总.md` / `RAG评估汇总表v2.xlsx`
- 生成层需根 `.env` 配置有效 `DEEPSEEK_API_KEY`；无 key 自动降级为仅检索层

已知环境限制：reranker（BAAI/bge-reranker-base，1.06GB ONNX）在低内存机器上
可能加载失败（ONNX bad allocation），此时按系统设计降级为粗排顺序，
iter03 结果与基线一致，需在内存充足环境重跑。
