# 内知 · KnowledgeQA —— 带权限的多 Agent 内部知识问答系统

上传内部文档（txt/md/pdf），系统异步切分并向量化入库；在会话中提问，服务端经**混合检索（向量 + BM25，RRF 融合，可选 rerank）**召回后调用 DeepSeek 生成答案并以 SSE 流式返回，答案附引用角标、可点击高亮跳回原文。内置**自研轻量多 Agent 编排**（Router / Planner / Executor / Reviewer），具备生产态能力：任务超时/重试/死信、模型超时降级、traceId 全链路、token 费用与配额、提示词注入防护、敏感工具调用人工确认。

## 架构

```
React+Vite 前端 ──REST/SSE(JWT)──▶ FastAPI 后端 ──SQL──▶ Postgres+pgvector
   │  Agent 步骤时间线                 │                    (users/sessions/messages/
   │  引用高亮/确认弹窗                ├── 上传/读取 ──▶ MinIO  tasks/quotas/documents/chunks)
                                     │                         ▲
DeepSeek API ◀── 仅服务端密钥流式调用 ──┤                         │
BGE embedding / bge-reranker(本地 ONNX) ◀── Worker 进程 ── 抢占 tasks 表 ─┘
```

- 前端禁止直连模型；DeepSeek 密钥只存在于 backend/worker 环境变量
- 前后端契约：后端 Pydantic → OpenAPI；前端 zod 运行时校验 + 可辨识联合 SSE 事件 + unknown 收窄；`npm run gen:types` 可由 OpenAPI 再生成 TS 类型交叉核对

## 快速开始

```bash
cp .env.example .env        # 填入 DEEPSEEK_API_KEY
docker compose up -d --build
# 前端 http://localhost:5173  演示账号 demo / demo1234
```

本地开发（无 Docker 时）：分别启动 Postgres(pgvector) 与 MinIO，`cd backend && uvicorn app.main:app --reload` + `python -m worker.main`，`cd frontend && npm run dev`。

## 目录

```
backend/   FastAPI 应用（app/）、任务 worker（worker/）、评测（eval/）、迁移（alembic/）
           app/services/agents/  多 Agent 编排（router/planner/orchestrator 等）
           app/services/rag.py   检索主链路（向量+BM25 RRF 融合）
           eval/ragbench/        离线 RAG 评估流水线（评估集 v2，13 个单变量实验）
frontend/  React+Vite（zod 契约、SSE hook、Agent 步骤时间线、shadcn 风格组件）
docs/      system-design/ 三篇设计练习；evidence/ 评测表与证据；依赖说明.md 各依赖职责
```

## 多 Agent 系统

**自研轻量编排，不引入 LangGraph**（FastAPI + httpx + Pydantic v2，async generator 事件流驱动），实现于 `backend/app/services/agents/`，以"角色协议 + 编排循环"替代图结构。

### 角色清单

| Agent | 位置 | 职责 |
| --- | --- | --- |
| **Router**（路由器） | `agents/router.py` | L4 查询分类：把改写后 query 分为 `factual/list/comparison/summary`，映射 top_k（3/10/10/8）；带 (session_id, sha256(query)) 缓存（TTL 300s、LRU 50 条）；失败回退 L2 启发式 `auto_top_k` |
| **Planner**（规划器） | `agents/planner.py` | 基于 query + 召回摘要产出 1-3 步计划（步骤类型 `retrieve/tool/answer`）；**只产自然语言意图，不生成工具参数**（参数由执行层原生 tools 通道生成） |
| **Executor**（执行器） | `agents/orchestrator.py` 循环体 | 非独立 LLM 角色：`retrieve` 步走向量+BM25 混合检索并做注入检测；`tool` 步走原生 tool_call 生成参数，只读工具直接执行，`delete_document` 走人工确认闸门 |
| **Reviewer**（校验器） | `agents/planner.py` | 对统一证据视图（≤10 份、每份截 300 字）做充分性判定；不足时以判定理由为 query **补充检索一轮**（之后不再复审，防死循环） |
| **Tool 层** | `app/services/tools.py` | `list_documents`（只读自动执行）/ `delete_document`（需 `POST /tools/confirm` 人工确认） |

所有角色经统一 `llm_client.chat()` 执行：JSON 结构化输出（Pydantic 强校验）、节点级超时、5xx 重试一次、Langfuse 埋点。

### 编排流程

```
用户 query（POST /chat/stream）
  ├─ 前置校验：会话归属 / 配额 / 落库消息
  ├─ query 改写（可开关，失败回退原文）
  ├─ top_k 决策：前端显式 > LLM Router（L4）> auto_top_k（L2 启发式）
  ├─ 首轮混合召回 + 注入检测 + 记忆召回注入
  ▼
  run_orchestrated（agent_orchestration_enabled 时）
   1) Planner 出计划（≤3 步；首轮失败即降级回旧回路）
   2) Executor 逐步执行，循环内每步检查：
      · 步数 ≥ agent_max_steps 或 token 预算耗尽 → 标记 skipped 退出
      · 客户端断连 → OrchestrationAborted 中止
      · retrieve 步 → 补充检索并入证据集
      · tool 步 → 原生 tools 流式调用；命中确认闸门 → pending_confirm，
        终止本轮编排（不跨请求恢复，用户确认后下一轮重新规划）
   3) Reviewer 校验（pending/超预算时跳过）→ 不足则补充检索一轮
  ├─ 终答：range(1) 单轮流式生成，补发 citation
  └─ 收尾：步骤轨迹落库（messages.tool_call, kind=agent_steps）→ usage → done
```

**防失控硬限制**：`AGENT_MAX_STEPS`（默认 4）、`AGENT_TOKEN_BUDGET`（默认 8000，仅计 Router/Planner/Reviewer，不含终答）、`AGENT_STEP_TIMEOUT`（默认 30s/节点）。**所有 Agent 节点失败都是降级而非报错**——任何环节异常都会回退到旧 `range(2)` 工具回路，保证对话可用。

### 配置开关（全部默认关闭，opt-in）

| 环境变量 | 默认 | 作用 |
| --- | --- | --- |
| `LLM_ROUTER_ENABLED` | false | L4 Router 分类路由 |
| `AGENT_ORCHESTRATION_ENABLED` | false | Planner-Executor-Reviewer 编排循环 |
| `AGENT_MAX_STEPS` | 4 | 计划步骤数上限 |
| `AGENT_TOKEN_BUDGET` | 8000 | Agent 节点 token 预算 |
| `AGENT_STEP_TIMEOUT` | 30.0 | 单节点超时（秒） |

前端以**可折叠步骤时间线**可视化编排过程（`AgentStepTimeline.tsx`）：router=路由 / plan=计划 / tool=执行 / review=校验，含 running/done/failed/skipped 状态与耗时；SSE 事件顺序契约：`agent_step* -> citation* -> agent_step* -> delta* -> (tool_call -> done) | (usage -> done) | error`。

## 检索链路详解（召回 / BM25 / Rerank）

主入口 `app/services/rag.py` 的 `retrieve()`，核心为**两路召回 + RRF 融合 + 可选 rerank + 断崖截断**。

### 向量召回

- Embedding：本地 **fastembed `BAAI/bge-small-zh-v1.5`**（512 维，ONNX/CPU）；另有 openai / sentence_transformers / hash 四种后端可切（hash 仅开发降级，生产启动校验禁止）
- Postgres 走 **pgvector** cosine distance 排序（IVFFlat 索引）；SQLite 走 Python 端余弦
- 只召回 child 块，按用户可见性过滤（本人 + 团队空间 + ACL 授权）

### BM25

- `app/services/bm25_index.py`：**`rank_bm25.BM25Okapi` + `jieba` 分词**，内存单例索引，以 `(child块数, max(created_at), team块数)` 为指纹懒重建（`asyncio.Lock` + `to_thread`）
- 全局放大 10 倍候选后再按用户权限过滤
- **降级链**：`BM25_ENABLED=false` 或依赖缺失 → 数据库回退（PG 用 tsvector `ts_rank`，SQLite 用 LIKE 计数）→ 再异常则空（不影响向量召回）

### Hybrid 融合（RRF）

- `_rrf_fuse()`：**Reciprocal Rank Fusion，k=60**，`score = Σ 1/(k+rank)`，非加权；两路各取候选后融合截断
- 开关 `HYBRID_SEARCH_ENABLED`（默认 true）。评测证实：**关掉 hybrid 召回率 -4pt、MRR -0.090，必须开启**

### Rerank

- `app/services/rerank.py`：**`BAAI/bge-reranker-base`**（fastembed `TextCrossEncoder`，懒加载单例，推理放 `to_thread`）
- 候选池 = `top_k × RERANK_CANDIDATE_MULTIPLIER`（默认 4）；`adaptive` 模式按分数断崖截断（降点 ≥ max(1.0, 2×中位数)，下限 3）
- 加载/推理失败 → 记 `rerank_degraded` 日志并**回退为粗排顺序截断**，不报错。默认 `RERANK_ENABLED=false`（非 Docker 环境 onnxruntime 不可用）

### top_k 决策（L2 / L4 两级）

- **L2 启发式** `auto_top_k()`：关键词规则判定 broad=10 / narrow=3 / default=5，零成本
- **L4 LLM Router**：factual=3 / list=10 / comparison=10 / summary=8，失败回退 L2

### 关键配置（`app/config.py`）

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `RAG_TOP_K` | 5 | 召回上限 |
| `HYBRID_SEARCH_ENABLED` / `BM25_ENABLED` | true / true | 混合检索与 BM25 开关 |
| `RERANK_ENABLED` / `RERANK_CANDIDATE_MULTIPLIER` | false / 4 | rerank 开关与候选池倍数 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 512 / 64 | 切分参数（入库时固化到 documents 表） |
| `CHUNK_STRATEGY` | window | window 滑动窗口 / semantic 父子块 |
| `EMBEDDING_BACKEND` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | fastembed / bge-small-zh-v1.5 / 512 | 向量后端 |

## 评测

### ragbench：离线 RAG 评估流水线（推荐，评估集 v2）

**评测集**：`backend/eval/dataset/questions_v2.jsonl`，50 题（factual 41 / comparison 5 / list 2 / summary 2，难例占比强制 ≥40%，多文档题 5）；语料 11 篇 = 8 篇领域文档 + 3 篇强干扰文档（含财务时限簇、SLA 簇等易混干扰）。构建与校验见 `dataset/README.md` 与 `gen_dataset.py`。

**gold 标注为 chunk 级、运行时解析**：chunk 所属文档 ∈ gold_docs 且内容含任一 gold_keyword（与 chunk_size 无关，跨切分参数稳健）。

**7 项指标**：

| 层 | 指标 | 口径 |
| --- | --- | --- |
| 检索层 | Recall@K | top_k 内命中 gold chunk 的比例 |
| 检索层 | Precision@K | 逐题 gold 块占召回块比例的均值 |
| 检索层 | MRR | 首命中倒数排名均值 |
| 生成层 | 忠实度 faithfulness | 答案拆原子论断后被上下文支持的比例 |
| 生成层 | 答案相关性 answer_relevance | LLM judge 按细则打分 |
| 生成层 | 上下文相关性 context_relevance | 相关块数 / 总块数 |
| 生成层 | 上下文召回 context_recall | 参考答案论断被上下文覆盖的比例 |

生成层用 DeepSeek 作 judge（JSON 结构化输出 + Pydantic 校验，重试 1 次，并发闸门 3，经 17 题人工抽检校准）。

**跑法**（详见 `backend/eval/README.md`）：

```powershell
# 环境：conda langgraph（首次 pip install -r backend/eval/ragbench/requirements.txt）
$env:PYTHONIOENCODING='utf-8'   # Windows 控制台必设

python -m eval.ragbench.experiments --list                      # 查看 12 个单变量实验
python -m eval.ragbench.experiments --only baseline             # 基线（仅检索层，秒级）
python -m eval.ragbench.experiments --only baseline --with-llm  # 基线（含生成层评审）
python -m eval.ragbench.experiments --all --with-llm            # 全部迭代
python -m eval.ragbench.experiments --custom mytag --set rerank=true --set top_k=8
python -m eval.ragbench.experiments --tags iter01-topk10,iter03-rerank --force
```

- 知识库按切分三要素缓存于 `results/_kb/`，语料指纹不变即复用
- **断点续跑**：已完成的题跳过；先跑检索层后加 `--with-llm` 自动补评审；同 tag 配置变更需 `--force`（自动归档旧明细）
- 结果：`results/<tag>/`（config.json / items.jsonl / summary.json）+ `docs/evidence/rag-v2-<tag>.md` 单轮报告 + `rag-v2-汇总.md` / `RAG评估汇总表v2.xlsx`
- 生成层需根 `.env` 配置有效 `DEEPSEEK_API_KEY`；无 key 自动降级为仅检索层

### 13 个单变量实验与结论（2026-10-12，50 题全量）

基线 = hybrid+BM25、无 rerank、top_k=5、512/64 window：**Recall 100% / Precision 26.0% / MRR 0.942 / 忠实度 97.31% / 答案相关性 95.80% / 上下文相关性 26.0% / 上下文召回 99.50%**

| 实验 | 变量 | 结论 |
| --- | --- | --- |
| iter01-topk10 | top_k 5→10 | 召回已饱和，Precision -13pt → **top_k=5 更优** |
| iter02-nohybrid | 关 hybrid 消融 | Recall -4pt、MRR -0.090 → **hybrid 必开** |
| iter03-rerank | 开 rerank | 本机内存不足加载失败（按设计降级），需在内存充足环境重跑 |
| iter04-rrf-k30 | RRF k 60→30 | 全指标不变，不敏感 |
| iter05-chunk256 | chunk 512→256 | Precision +6pt，但 MRR -0.012 |
| iter06-chunk1024 | chunk 512→1024 | MRR 全场最高 0.970，但 Precision -4pt |
| **iter07-overlap128** | overlap 64→128 | **全场唯一全赢**：Precision +4pt、MRR +0.013、答案相关性 +1.8pt |
| iter08-semantic | 父子块切分 | MRR +0.025、忠实度最高，但 Precision -2pt |
| iter09-auto-topk | L2 启发式 | 零成本小胜：Precision +1.2pt、上下文相关性 +3.9pt，MRR 无损 |
| iter10-router | L4 LLM Router | Precision **+9.55pt**、上下文相关性 **+11.46pt**（双料最高）；代价 MRR -0.032 + 每查询一次 LLM 调用 |
| iter11-context3 | 注入块 5→3 | 上下文相关性 +14pt 但答案相关性 -2.6pt → 维持 5 块 |
| iter12-prompt-concise | 简洁 prompt | 基本中性 → 维持默认 |

**最佳组合（已验证无负面交互）= `CHUNK_OVERLAP=128` + L2 `auto_top_k`**：7 项指标 5 升 2 平 0 降 —— Precision 26%→**31.53%**、MRR 0.955、忠实度 97.87%、答案相关性 97.0%、Recall 100% 持平。可选再开 `LLM_ROUTER_ENABLED` 换取 Precision/上下文相关性全场最优（代价 MRR -3.2pt）。

### 旧版在线评测（30 题，两组切分参数对比）

```bash
docker compose exec backend python -m eval.run_eval --tag baseline
# 改 .env 切分参数、重建文档后
docker compose exec backend python -m eval.run_eval --tag tuned
docker compose exec backend python -m eval.run_eval --compare baseline tuned
```

输出 `results/eval_{tag}.jsonl` / `eval_{tag}_summary.json` / `compare_{a}_vs_{b}.csv`。

## 功能清单

| 能力 | 实现 |
| --- | --- |
| 登录鉴权 | JWT（PyJWT + bcrypt），按用户隔离会话/文档/配额 |
| 流式对话 | 服务端 SSE 代理 DeepSeek；前端 fetch+ReadableStream 打字机、AbortController 停止、失败态可重试 |
| RAG 闭环 | MinIO 上传 → tasks 表异步切分（参数可配）→ 本地 BGE embedding → pgvector → **向量+BM25 RRF 混合召回（可选 rerank）** → citation 事件 → 引用面板高亮原文 |
| 多 Agent 编排 | Router 分类路由 + Planner/Executor/Reviewer 循环，步骤时间线可视化，失败即降级旧回路 |
| 记忆与改写 | query 改写、L2 会话摘要、L3 记忆抽取（均为异步任务，可开关） |
| 权限 | 团队空间 + DocumentGrant ACL，检索全程按可见性过滤 |
| 工具人工确认 | `delete_document` 由模型发起 tool_call → 落库 pending_confirm → 前端弹窗确认 → 后端执行并留痕；`list_documents` 只读自动执行 |
| 超时/重试/死信 | worker `FOR UPDATE SKIP LOCKED` 抢占；`asyncio.wait_for` 超时；指数退避重试；超限置 dead |
| 降级 | 模型超时/异常 → SSE error 事件；召回失败降级为空召回；rerank/Router/编排失败各自降级不报错 |
| traceId | 中间件生成/透传，贯穿日志、SSE 事件、任务、费用记录 |
| 费用/配额 | DeepSeek 流末 usage 按价目表折算，累计 quotas 表；前端配额角标，超限拒绝提问 |
| 注入防护 | 召回文本包裹分隔符 + 系统提示声明为数据；正则检测命中即告警留痕（样例见安全规范.md） |

## 四问（数据 / 失败 / 费用 / 评测）

- **数据**：文档原文存 MinIO，切分块与 512 维向量存 pgvector，按 user_id + 团队 + ACL 隔离召回；七张表见 `backend/alembic/versions/0001_init.py`
- **失败**：任务超时重试 3 次（5s→10s→20s 退避）后进死信；模型 60s 超时降级为失败态并返回 error 事件；流中断标记 aborted；Agent 节点失败统一降级回旧回路
- **费用**：usage 按输入 ¥2/M、输出 ¥8/M tokens（可在 .env 调整）折算，按用户按月累计，配额默认 100 万 tokens/月
- **评测**：ragbench 7 项指标 + 13 个单变量实验，最佳组合与逐轮 delta 见 `docs/evidence/rag-v2-*.md`

## 证据索引（docs/evidence/）

- `rag-v2-评估总结报告.md`：13 轮实验完整结论与落地建议；`RAG评估汇总表v2.xlsx`：逐轮指标对比
- `rag-v2-best-combo.md` / `rag-v2-iter*.md`：最佳组合与各单变量实验的 delta 报告
- `RAG评测对比表.xlsx`：旧版评测前后对比（含逐条明细与命中率公式）
- `trace-追踪样例.md`：一次完整请求追踪（traceId 贯穿前端 → API → SSE → 任务 → 费用）
- `deadletter-死信演示.md`：一次超时进死信的完整操作与日志
- `rollback-回滚说明.md`：迁移回滚与版本回滚操作说明
- `录屏脚本.md`：两分钟演示录屏的分镜脚本

## 虚机部署

见 [`docs/deploy-vm.md`](docs/deploy-vm.md)：虚机规格、Docker 安装、配置、启动、访问、反代 HTTPS、常见坑。
