# 执行计划 — 文档增量更新与失效检测

按序执行；每步完成后跑对应校验。回滚点：步骤 2（迁移 downgrade）、步骤 6 前任意 `git checkout`。

## 1. 数据层 + 迁移

- [ ] `backend/app/models/document.py`：加 `version` / `ingest_signature` / `ingested_at` 三列。
- [ ] `backend/alembic/versions/0012_document_version_ingest.py`：add_column × 3 + ready 行签名回填（env 推导，默认值对齐 `Settings`）；downgrade drop_column × 3。
- 校验：`cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`（需本地 pg 或 docker）。

## 2. 失效检测服务

- [ ] `backend/app/services/doc_sync.py`：`current_ingest_signature` / `signature_of` / `stale_reasons` / `is_stale`。
- [ ] `worker/main.py`：`ingest_document` 成功路径写 `ingest_signature` + `ingested_at`。
- 校验：改 `CHUNK_SIZE` 重启后，ready 文档 `stale_reasons` 非空（可用 REPL/临时脚本断言）。

## 3. 后端端点

- [ ] `schemas/document.py`：`DocumentOut` 加 4 字段；新增 `ContentUpdateResult`。
- [ ] `api/documents.py`：
  - [ ] `_to_out()` 统一序列化（含 stale 计算），`GET /documents`、`GET /documents/{id}` 切换。
  - [ ] `POST /documents/{id}/content`（含 no_text 内联清 chunks、409 竞争/重复分支）。
  - [ ] `POST /documents/{id}/reingest`。
- [ ] 上传端点新建 Document 时初始化 `ingest_signature=""`（依赖 worker 成功后写入）。
- 校验（手工或脚本）：
  - 上传 A → content 传同字节 → `updated=false`、无新 task 行。
  - content 传新字节 → `version=2`、status 流转 uploaded→processing→ready、旧 chunks 被替换（chunk_count 变化）。
  - content 传与文档 B 相同字节 → 409 `DUPLICATE_DOCUMENT`。
  - processing 中调 content/reingest → 409。
  - ready 文档 content 传纯图片 PDF → `no_text` 且 chunks=0。
  - `GET /documents` 返回 `stale`/`stale_reasons`/`version`/`ingested_at`。

## 4. 前端

- [ ] `api/schemas.ts`：`DocumentSchema` 加 4 字段。
- [ ] `pages/DocumentsPage.tsx`：`v{n}` 版本号、stale 徽标（title 展示原因）、`RefreshCw` 一键刷新（stale/failed 可见）、`FileUp` 更新内容入口（含 `updated=false` 提示）。
- 校验：`cd frontend && npm run build`（tsc + vite）通过；页面手测徽标出现/消失。

## 5. 质量检查

- [ ] 后端 lint/类型（项目既有命令，参考 `.trellis/spec/backend/quality-guidelines.md`）。
- [ ] `read_lints` 无新增错误。
- [ ] 对照 `.trellis/spec/backend/documents-api.md` 更新其中端点清单与状态机说明（Phase 3.3 spec 更新）。

## 回滚

- API/worker/schema 改动：`git checkout` 单文件即可。
- 迁移：`alembic downgrade 0011_usage_records` 后删 0012 文件。
- 前端：`git checkout`。
