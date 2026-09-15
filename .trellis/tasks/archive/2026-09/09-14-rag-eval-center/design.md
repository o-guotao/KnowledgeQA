# RAG 评测中心 — 技术设计

## 结论先行

- 评测执行**不进 web 请求**：`tasks` 表新增 `run_eval` 任务类型，worker 异步跑，状态机复用（pending/running/done/failed/dead），页面轮询——与文档入库同一模式。
- 评测知识库**独立临时 sqlite**（沿用现有脚本模式）：不与线上库混跑，避免权限/团队可见性干扰，run 结束即删。
- 图表库 **Recharts**（`admin` chunk 懒加载）；其余全部复用现有栈，零新中间件。

## 数据模型（迁移 `0014_eval_center`）

```text
eval_datasets
  id UUID pk | name String(128) | source String(16)  # builtin | upload
  item_count Integer | payload Text(jsonl 原文，≤1MB) | created_at

eval_runs
  id UUID pk | dataset_id FK→eval_datasets(SET NULL) | name String(128)
  config JSON          # {"groups":[...],"top_k_max":10,"with_llm":false,
                       #  "chunk_size":128,"chunk_overlap":32,"embedding_backend":"fastembed","embedding_model":"..."}
  status String(16)    # pending | running | done | failed
  summary JSON         # {"<group>": {"recall_at_k": {"1":..,"5":..}, "mrr": ..,
                       #   "answer_hit_rate": 0.83,                # with_llm 时才有
                       #   "latency_ms": {"embed_avg":..,"recall_avg":..,"rerank_avg":..,"llm_avg":..}}}
  error Text nullable | duration_ms Float nullable
  created_at / finished_at

eval_run_items
  id UUID pk | run_id FK→eval_runs(CASCADE) | idx Integer
  question Text | gold_doc String(256)
  ranks JSON           # {"<group>": {"rank": 3, "hit": true, "cited": [...],
                       #   "answer_hit": true, "injection_blocked": true,  # with_llm 时才有
                       #   "latency_ms": {"embed":..,"recall":..,"rerank":..,"llm":..}}}

usage_records（既有表加列，随 0014 一起）
  + ttft_ms Float nullable      # LLM 首 token 耗时
  + total_ms Float nullable     # 端到端总耗时
  + recall_ms Float nullable    # 召回（向量+关键词+RRF）耗时
  + rerank_ms Float nullable    # 重排耗时（未开启为 NULL）
```

索引：`eval_run_items(run_id)`、`eval_runs(status, created_at)`；usage_records 既有索引够用（按日聚合走 created_at）。

## 执行器（`services/eval_runner.py`）

抽取 `eval/run_recall_eval.py` 的 setup/run_group 逻辑，改造点：

1. **入库来源**：文档语料固定用 `eval/sample_docs/`（与线上文档无关）；问句来自 dataset.payload（jsonl 解析，字段 `q`/`gold_doc`/`gold_keywords`，非法行收集报错）。
2. **配置矩阵**：组定义 `(tag, hybrid, bm25, rerank)` 四组；逐组 `get_settings.cache_clear()` + 覆盖 env（沿用脚本技巧）+ 重置 rerank 单例；BM25 索引单例同样重置（`bm25_index._state = None`）。
3. **top_k 扫描**：每组配置对每题 retrieve 一次取 `top_k=10`，按 K=1..10 截断算 recall@K（一次召回多次复用，成本不翻 10 倍）。
4. **分阶段计时**：`time.perf_counter()` 包 embed_query / retrieve / rerank 调用点，写入 item.ranks[group].latency_ms，汇总取均值。
5. **LLM 答案正确率**（`with_llm=true`）：召回后用与线上一致的 prompt 装配（`build_rag_user_content`）调 provider 生成回答（复用 `services/deepseek.py` / model_configs 解析逻辑，非流式一次调用），判 `gold_keywords` 命中率；样例集注入题的 `injection_blocked` 标记（回答未执行注入指令且服务端有 injection 告警）。答案全文不存（省空间），只存命中布尔。token 成本：4 组 × 30 题 ≈ 120 次调用/run，弹窗明示。
6. **隔离**：`EVAL_DB=sqlite:///./.eval_run_<run_id>.db`，临时 engine 建表跑完删除；**注意** `app.db.SessionLocal` 是全局单例——执行器自建 engine/session（不碰全局），embedding 服务复用全局单例（无状态）。
7. **worker 接入**：`worker/main.py::run_task` 加 `run_eval` 分支；超时沿用 `task_timeout_seconds`（不含 LLM 约 2-5 分钟；`with_llm` 另加约 3-8 分钟，发起时按 with_llm 放宽 timeout 或 max_retries=0 不重试）。

### 线上耗时采集

- `chat.py` SSE 链路在 召回前/重排后/首个 token/流结束 四处打点（`time.perf_counter()`），写入既有 `UsageRecord` 新列（与现有 accumulate_usage 同一事务，不增请求级开销）。
- `GET /admin/eval/online-stats?days=14`：`usage_records` 按日聚合 `percentile_cont(0.5/0.95)`（pg；sqlite 用排序近似）→ `[{date, p50, p95, calls}]` + feedback down_rate（复用 `api/feedback.py` 聚合口径）。

## API（`api/admin/eval.py`，挂在 admin 路由族，统一 `require_admin`）

```text
GET    /admin/eval/datasets                 列表
POST   /admin/eval/datasets/import-builtin  内置 questions.jsonl / questions_hard.jsonl 一键导入
POST   /admin/eval/datasets                 上传 jsonl（multipart，≤1MB，逐行校验）
DELETE /admin/eval/datasets/{id}
GET    /admin/eval/runs?dataset_id=         列表（含状态）
POST   /admin/eval/runs                     发起 {dataset_id, groups[], top_k_max, name?} → 202 + run
GET    /admin/eval/runs/{id}                详情（summary + items）
GET    /admin/eval/runs/{id}/items.csv      明细导出
GET    /admin/eval/online-stats?days=14     线上按日 p50/p95 延迟 + 点踩率
对比由前端取两个 run 详情自行渲染（不做专门对比端点，YAGNI）
```

并发约束：同一时刻只允许一个 running/pending 的 run（发起时检查，409 `EVAL_RUN_BUSY`）——评测独占 embedding/CPU，避免互相污染延迟数据。

## 前端（AdminPage 加 Tab）

- `AdminPage` 现有结构是单页多区块 → 改 Tab：用户管理 / 用量看板 / **评测中心**（组件拆到 `pages/admin/EvalCenterTab.tsx`，AdminPage 壳不动）。
- 组件：KPI 卡条、GroupBarChart（Recall@5+MRR，with_llm run 加答案正确率系列）、TopKLineChart（多配置线，实/虚线+直接标注）、OnlineLatencyChart（按日 p50/p95 双折线+点踩率卡）、RunList（勾选两个 → 对比视图）、RunDetailTable（↑↓ 符号+颜色双编码）、NewRunDialog（含 with_llm 开关与 token 成本提示）。
- Recharts：`import("recharts")` 动态引入 EvalCenterTab（Vite 自动分包）；zod schema 校验 API 响应。
- 运行中 run：5s 轮询（复用文档页模式），完成/失败停止。

## 明确不做

CI 门禁、数据集在线编辑、Langfuse 联动。

## 风险与决策

| 风险 | 决策 |
|---|---|
| get_settings 全局缓存被评测 env 污染 | 评测在 worker 进程跑，与 web 进程隔离；进程内每组后恢复 |
| 全局 SessionLocal/engine 绑定线上库 | 执行器自建临时 engine，结束后 dispose + 删文件 |
| BM25/rerank 单例跨组污染 | 每组重置单例（沿用脚本 rk._reranker=None 模式，bm25 同样处理） |
| 评测打满 CPU 影响线上问答 | 并发=1（EVAL_RUN_BUSY）；OMP_NUM_THREADS 已限；文档提示低峰跑 |
| jsonl 上传注入/超大 | ≤1MB + 逐行 schema 校验 + 条目数上限 500 |
| with_llm 失控成本 | 默认关闭 + 弹窗明示成本 + 条目数上限 500 封顶（≈2000 次调用上限） |
| 线上打点增延迟 | 4 个 perf_counter 调用（纳秒级），写库复用既有事务 |
