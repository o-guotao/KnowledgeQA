# 内知 · KnowledgeQA —— 带权限的内部知识问答 Agent

上传内部文档（txt/md/pdf），系统异步切分并向量化入库；在会话中提问，服务端经 RAG 召回后调用 DeepSeek 生成答案并以 SSE 流式返回，答案附引用角标、可点击高亮跳回原文。具备生产态能力：任务超时/重试/死信、模型超时降级、traceId 全链路、token 费用与配额、提示词注入防护样例、敏感工具调用人工确认。

## 架构

```
React+Vite 前端 ──REST/SSE(JWT)──▶ FastAPI 后端 ──SQL──▶ Postgres+pgvector
                                     │                    (users/sessions/messages/
                                     ├── 上传/读取 ──▶ MinIO  tasks/quotas/documents/chunks)
                                     │                         ▲
DeepSeek API ◀── 仅服务端密钥流式调用 ──┘                         │
BGE embedding(本地 ONNX) ◀── Worker 进程 ── 抢占 tasks 表 ────────┘
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
frontend/  React+Vite（zod 契约、SSE hook、shadcn 风格组件）
docs/      system-design/ 三篇设计练习；evidence/ 评测表与证据；依赖说明.md 各依赖职责
```

## 功能清单

| 能力 | 实现 |
| --- | --- |
| 登录鉴权 | JWT（PyJWT + bcrypt），按用户隔离会话/文档/配额 |
| 流式对话 | 服务端 SSE 代理 DeepSeek；前端 fetch+ReadableStream 打字机、AbortController 停止、失败态可重试 |
| RAG 闭环 | MinIO 上传 → tasks 表异步切分（参数可配）→ 本地 BGE embedding → pgvector IVFFlat → top-k 召回 → citation 事件 → 引用面板高亮原文 |
| 工具人工确认 | `delete_document` 由模型发起 tool_call → 落库 pending_confirm → 前端弹窗确认 → 后端执行并留痕；`list_documents` 只读自动执行 |
| 超时/重试/死信 | worker `FOR UPDATE SKIP LOCKED` 抢占；`asyncio.wait_for` 超时；指数退避重试；超限置 dead |
| 降级 | 模型超时/异常 → SSE error 事件 + 失败态；召回失败降级为空召回并记日志 |
| traceId | 中间件生成/透传，贯穿日志、SSE 事件、任务、费用记录 |
| 费用/配额 | DeepSeek 流末 usage 按价目表折算，累计 quotas 表；前端配额角标，超限拒绝提问 |
| 注入防护 | 召回文本包裹分隔符 + 系统提示声明为数据；正则检测命中即告警留痕（样例见安全规范.md） |

## 评测

30 条事实型问句（`backend/eval/questions.jsonl`），指标为召回命中率与回答正确率。
两组切分参数对比流程见 `backend/eval/README.md`；对比表：`docs/evidence/RAG评测对比表.xlsx`（跑完用 `make_eval_xlsx.py` 自动填数）。

## 四问（数据 / 失败 / 费用 / 评测）

- **数据**：文档原文存 MinIO，切分块与 512 维向量存 pgvector，按 user_id 隔离召回；七张表见 `backend/alembic/versions/0001_init.py`
- **失败**：任务超时重试 3 次（5s→10s→20s 退避）后进死信；模型 60s 超时降级为失败态并返回 error 事件；流中断标记 aborted
- **费用**：usage 按输入 ¥2/M、输出 ¥8/M tokens（可在 .env 调整）折算，按用户按月累计，配额默认 100 万 tokens/月
- **评测**：召回命中率 + 回答正确率，切分参数调整后数字可升可降，对比表见 docs/evidence/

## 证据索引（docs/evidence/）

- `RAG评测对比表.xlsx`：评测前后对比（含逐条明细与命中率公式）
- `trace-追踪样例.md`：一次完整请求追踪（traceId 贯穿前端 → API → SSE → 任务 → 费用）
- `deadletter-死信演示.md`：一次超时进死信的完整操作与日志
- `rollback-回滚说明.md`：迁移回滚与版本回滚操作说明
- `录屏脚本.md`：两分钟演示录屏的分镜脚本

## 虚机部署

见 [`docs/deploy-vm.md`](docs/deploy-vm.md)：虚机规格、Docker 安装、配置、启动、访问、反代 HTTPS、常见坑。
