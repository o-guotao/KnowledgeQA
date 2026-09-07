# 父任务执行计划（集成）

父任务本身无直接实现，负责排序与集成验收。两个子任务独立规划、实现、校验、归档：

1. `09-07-batch-upload-validation` — 先做（其改动集中在 `backend/app/api/documents.py`、`models/document.py`、`schemas/document.py` + 迁移，以及 `DocumentsPage.tsx` 批量区）。
2. `09-07-document-preview` — 后做（新增后端 file 接口 + `DocumentsPage.tsx` 预览区，与子任务 1 同文件，需排序）。

## 验证命令

- 后端单测/语法：`docker compose exec backend python -c "import app.main"`；迁移 `docker compose exec backend alembic upgrade head`。
- 端到端（curl 带 token）：
  - 单文件上传正常 → 201，`DocumentOut` 含 `content_hash`。
  - 同名文件二次上传 → `DUPLICATE_DOCUMENT` 409。
  - 改名重传同一内容 → 409。
  - 纯图片 PDF → 201 + status `no_text`，任务表无 ingest 任务。
  - 非法文件名/超长 → 400 `INVALID_FILENAME`。
- 前端：`npm run build`（tsc 类型含新状态/哈希）；`npm run gen:types` 刷新 schema.d.ts。
- 集成回归（两个子任务均合入后）：批量多选混合 合法/重复/非法名/纯图 PDF → 结果面板逐条正确；打开每类文档预览；删除、轮询不回归。

## Review Gate（start 前）

- prd/design/implement 三者一致；两子任务契约（`no_text`、错误码、文件名规则、content_hash）与父 design 完全一致。
- 子任务各自 prd.md 的 acceptance 可测。

## 回滚点

- 每子任务独立可回滚：迁移 down、前端按 commit 回退。
