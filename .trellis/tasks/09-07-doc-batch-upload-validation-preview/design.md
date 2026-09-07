# 文档批量上传、校验与预览 — 技术设计

## 架构边界与子任务契约

两个子任务共享**状态枚举命名**与**错误码约定**，此处统一定义，双方必须遵守：

- 新增终态枚举名：`no_text`（标签「不可检索」）。只在 `backend/app/models/document.py` 的 `DOCUMENT_STATUSES`、`frontend/src/api/schemas.ts` 的 `DocumentSchema.status` z.enum、`DocumentsPage.STATUS_META` 三处扩展；不进入 `PENDING_STATUSES`（不轮询）。
- 新增错误码（字符串，沿用 `AppError`）：`DUPLICATE_DOCUMENT`(409)、`INVALID_FILENAME`(400)、复用 `FILE_TOO_LARGE`/`BAD_FILE_TYPE`/`EMPTY_FILE`。响应形态沿用 `{detail:{code,message}}`。
- 文件名规则（前后端同一套）：取 basename；拒绝控制字符与 `<>:"/\\|?*`；去首尾空白与 `.`；长度 1..255。
- 重复判定：内容 SHA-256。`content_hash` 仅用于本人、未删除文档比对。

## 数据流

```
上传（逐文件，前端串行调用现有 POST /api/documents）
  → 前端预检：类型/大小/文件名/库内哈希判重/批内去重
  → 后端权威：read bytes → 文件名规范化 → 空/大小/类型校验
                → sha256 → 判重(409)
                → 若 PDF：pypdf 试提文本 → 空则 status=no_text（不投递 worker）
                → 否则落库(带 content_hash) + 入队切分任务
  → DocumentOut 返回（含 status、content_hash）
预览（打开列表任意文档）
  → GET /api/documents/{id}/file（鉴权，MinIO 取字节，按扩展名给 content-type）
  → .txt/.md 文本；.pdf pdf.js 逐页渲染（统一覆盖文字/纯图两类 PDF）
```

## 关键取舍

1. **批量传输形态 = 前端逐文件串行调用现有单文件接口，不新增多文件接口。**
   - 理由：前端与 deploy 两层 nginx `client_max_body_size` 均为 25m（`frontend/nginx.conf`、`deploy/nginx/nginx.conf:34`）。若单请求多文件，几份 20MB 文件即可超总限，需同步调高两层 nginx 并在内存里整段缓冲多文件，风险大于收益。逐文件调用天然逐文件进度、失败隔离、判重也能前后一致性（后传的文件会看到先传文件已入库）。
   - 代价：无单请求事务性批量；N 个请求。内部工具可接受。
   - 若未来要真·批量端点，另开任务，不在此范围。
2. **图片型 PDF 检测放在上传端点**（与现有校验同函数内），失败不再进 worker。判据与 worker 现有一致：pypdf 全页提取文本为空 → `no_text`。
3. **判重权威在后端**：前端哈希预检仅减少无效请求，最终以后端 409 为准；DB 加**部分唯一索引** `(user_id, content_hash) WHERE content_hash IS NOT NULL` 兜底并发。
4. **预览 PDF 统一走 pdf.js 浏览器端渲染**（一条路径覆盖文字/纯图 PDF，保真、免后端渲染服务）。txt/md 直接解码文本。后端仅新增一个带鉴权的原始字节接口，无预签名 URL。

## 兼容与迁移

- Alembic revision：`documents` 加 `content_hash String(64) nullable`；部分唯一索引。存量行 content_hash=NULL，可读、不参与哈希判重（仅文件名粗查，已记录为限制）。
- `no_text` 对既有查询透明：检索只取 `status='ready'` 的 chunk，天然排除；删除/列表逻辑按 user_id 不因状态改变而回归。
- worker `ingest_document` 入口不变，只是 `no_text` 文档不会被投递，故不受影响；若被误投递（如历史任务）仍走原逻辑，无害。

## 运维 / 回滚

- 回滚点：迁移 revision 可 down（去掉列/索引）；后端与前端新枚举在回滚时无破坏（旧前端忽略新状态则显示兜底）。
- pdfjs-dist 走 npm，Vite worker 需配置 `?url` 或 GlobalWorkerOptions；若体积敏感，仅在需要预览 PDF 时动态 import。

## 跨子任务验收顺序

先合入 `09-07-batch-upload-validation`（同一批文件被两个子任务改动最多的 `DocumentsPage.tsx`），再合入 `09-07-document-preview`，避免同文件合并冲突；两者验收独立但在最后做一次集成回归（见 implement.md 第 7 步）。
