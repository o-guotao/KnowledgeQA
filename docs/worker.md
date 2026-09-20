# Worker 任务执行进程

> 结论先行：worker 是与 FastAPI 后台**同镜像、仅入口不同**的独立常驻进程，是系统的异步任务
> 消费者。API 进程只负责「收请求、写任务、查状态」，所有 CPU/模型密集的慢活（文档切块 +
> embedding、RAG 评测）都由 worker 轮询 `tasks` 表抢占执行。两者只通过 `tasks` 表和文档状态
> 字段通信，互相无直接调用，因此可独立扩缩容、独立重启。
> 源：`backend/worker/main.py`、`backend/app/api/documents.py`、`docker-compose.yml`。

---

## 一、整体链路

```
用户上传文档 / 发起评测
  │
  ├─[API 进程] 校验 → 写 tasks 表（status=pending，payload 只带 id）→ 立即返回
  │
  ├─[worker 进程] 每 2s 轮询 → 抢占（status=running）→ 执行 → done / failed / dead
  │      ├─ ingest_document：取文件 → 提取文本 → 切块 → embedding → 写 chunks → 文档 ready
  │      └─ run_eval：4 组配置矩阵跑召回指标（可选 LLM 评分）
  │
  └─[前端] 轮询 documents.status，「切分中」变「已入库」；RAG 问答读取 chunks
```

## 二、启动与部署形态

worker 没有网络入口，不暴露任何端口，唯一输入是轮询数据库。

| 环境 | 启动方式 | 说明 |
| --- | --- | --- |
| 生产（docker-compose） | `command: python -m worker.main`，与 backend **同镜像** | `depends_on: backend (service_healthy)`，等 alembic 迁移完成后才启动；`mem_limit: 1536m`（BGE 模型 + 推理是内存大头，backend 为 768m） |
| 本地开发 | 另开终端 `python -m worker.main` | 与 uvicorn 进程相互独立，改 `chunking.py` 等只需重启 worker 生效 |

启动时自检（`main()`，先于任务循环）：

1. **sqlite 模式自行建表**（`_init_sqlite_if_needed`）：worker 可能先于 API 启动，不能假设表已存在
2. **embedding 后端校验**（`_verify_embedding_on_start`）：worker 是实际执行 embedding 的进程，
   生产环境不可用直接 fail fast 退出——否则所有切分任务会静默失败进死信

## 三、任务类型

| 任务类型 | 投递方 | 执行内容 | 超时 |
| --- | --- | --- | --- |
| `ingest_document` | 上传文档 / 就地更新 / reingest 重切（`documents.py`） | 对象存储取文件 → `extract_text` 提取文本（txt/md/PDF(pdfplumber)/docx/xlsx）→ 切块（window 滑动窗口 或 semantic 父子块）→ 批量 embedding → 写 `chunks` 表 → 文档置 `ready`，记录 `ingest_signature`（配置快照，供 stale 失效检测）与 `ingested_at` | `task_timeout_seconds`（默认 300s） |
| `run_eval` | 评测中心发起（`admin_eval.py`） | 4 组配置矩阵（baseline/hybrid/+BM25/+rerank）跑召回指标，可选 LLM 答案正确率评分 | `eval_task_timeout_seconds`（默认 1800s） |
| `demo_fail` | 调试 | 恒超时，验证「超时 → 重试 → 死信」链路 | — |

任务 payload 只带 id（如 `{"document_id": "..."}`），worker 自己回库取数据、去对象存储取文件。

## 四、任务状态机与可靠性设计

```
pending ──抢占──> running ──成功──> done
                  │  失败/超时
                  └──> failed（next_run_at = now + base*2^n，指数退避重试）
                            │ 超过 max_retries（默认 3）
                            └──> dead（死信，不再重试）
```

| 机制 | 实现 | 覆盖场景 |
| --- | --- | --- |
| 抢占防重 | Postgres `FOR UPDATE SKIP LOCKED`（`claim_task`）；SQLite 单 worker 用 SELECT+UPDATE | 多 worker 并发抢同一任务 |
| 超时控制 | `asyncio.wait_for`，普通任务与评测任务独立超时 | 慢文件/慢模型拖死队列 |
| 指数退避 | `next_run_at = now + task_retry_base_seconds × 2^(n-1)`（`handle_failure`） | 临时性故障（网络抖动、模型加载慢） |
| 死信 | 超过 `max_retries` 置 `dead` | 永久性故障（损坏文件、配置错误）不再空转 |
| 僵尸回收 | 每 ~60s 巡检 `running` 超 2 倍 timeout 的任务，重置回 `failed` 重走重试流程（`reap_stuck_running`） | worker 崩溃 / OOM / 断电后任务卡死 |
| 幂等重放 | `ingest_document` 先 `DELETE` 旧 chunks 再写新块，chunk 写入以 document_id 事务包裹 | 任务重复执行不产生重复数据 |
| 失败联动 | 任务失败同步把文档置 `failed` 并记录 error（`mark_document_failed`） | 前端可见失败原因，可一键重试 |

## 五、执行结果的消费方

worker 的产出不是返回值，而是数据库状态：

| 写入 | 消费方 |
| --- | --- |
| `chunks` 表（切块文本 + 向量 + 父子块关系） | 问答时 RAG 检索（向量/BM25 召回、引用回跳） |
| `documents.status`（uploaded → processing → ready/failed） | 前端文档列表轮询刷新进度；`no_text` 终态（图片/无文字层 PDF）由上传时前置判定，worker 不参与 |
| `documents.ingest_signature` + `ingested_at` | stale 失效检测（切分/embedding 配置变更后提示「需刷新」，reingest 一键重切） |
| `tasks.status` / `error` / `duration_ms` / `retry_count` | 任务审计与排障（谁的任务、跑了多久、失败原因、重试几次） |

## 六、运维要点

- **改了提取/切块代码只重启 worker**：`extract_text`、切分策略、embedding 相关改动在 worker 进程生效，
  API 进程的 `_detect_status` 探测走同一份代码但独立进程，需两边都重启
- **多实例**：Postgres 下 `SKIP LOCKED` 天然支持多 worker 横向扩容；注意 `docker-compose.yml` 中
  `OMP_NUM_THREADS` 限制 ONNX/fastembed 线程数，避免多 worker 抢满 CPU
- **日志**：worker 日志独立文件（本地 `worker.out.log` / `worker.err.log`，容器走 json-file 轮转
  10MB×3），任务执行带 `trace_id`（从上传请求贯穿到 worker，可串联排查）
- **死信处理**：`dead` 任务不会自动清理；定位修复问题后，把 `tasks.status` 改回 `pending` 并
  `next_run_at` 置当前时间即可重新入队
