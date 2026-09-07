# 批量上传与上传校验 — 执行计划

按序实施，每步后自检。**参照父 design 契约**（枚举名 `no_text`、错误码、文件名规则、content_hash）。

## 1. 后端：迁移 + 模型
- `backend/alembic/versions/0XXX_document_content_hash.py`：`documents.content_hash String(64) nullable` + 部分唯一索引 `(user_id, content_hash) WHERE content_hash IS NOT NULL`。
- `backend/app/models/document.py`：加列、`DOCUMENT_STATUSES += ("no_text",)`。
- 验证：`docker compose exec backend alembic upgrade head`；`\d documents` 见列与索引。

## 2. 后端：文件名规范化与哈希判重
- 在 `backend/app/api/documents.py` 抽出 `_normalize_filename(raw) -> str`（抛 `INVALID_FILENAME`）与 `_hash(data)`。
- 端点按 design 步骤 3/4/5 插入；判重查询；catch IntegrityError → 409 DUPLICATE_DOCUMENT。
- 验证：pytest/手动 curl——非法名 400、重复 409、改名重传 409、同名不同内容 201。

## 3. 后端：图片型 PDF → no_text
- 上传端点步骤 6：pdf 预检 `extract_text` 为空 → 状态 `no_text`、不建 Task。
- 验证：上传上一份纯图片样例 PDF → 201 + status `no_text`；`SELECT count(*) FROM tasks WHERE type='ingest_document' AND payload->>'document_id'=<id>` = 0；文档列表可见。

## 4. 后端：DocumentOut + openapi
- `backend/app/schemas/document.py` `DocumentOut.content_hash: str | None`。
- 验证：`DocumentOut.model_validate` 正常、响应含字段。

## 5. 前端：schema + 类型
- `frontend/src/api/schemas.ts` `DocumentSchema` 加 `content_hash: z.string().nullable()`，status 枚举加 `"no_text"`。
- `npm run gen:types`（如后端可达）；`npm run build` 通过。

## 6. 前端：DocumentsPage 批量 + 预检 + 结果面板
- 重写 `upload`/input：`multiple`、任务数组、预检 util、逐文件串行、内联结果列表；删 alert。
- `STATUS_META` 增 `no_text`；说明文案微调。
- 验证：`npm run build`；手动——一次多选 合法×2+重复+超长名+纯图 PDF → 面板逐条正确；合法项入库、列表出现。

## 7. Review Gate（本子任务）
- 对照 `prd.md` acceptance 全绿；`no_text`/错误码/文件名规则与父 design 契约一致；`alembic down` 可回滚验证一次（在功能验收完成后）。

## 风险文件 / 回滚点
- `documents.py`、`models/document.py`、`DocumentsPage.tsx`（后者会与 preview 子任务共享，本任务完成即合入，见父 implement 排序）。
