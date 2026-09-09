# 批量上传与上传校验 — 技术设计

## 结论先行

- **不新增多文件后端接口**：前端多选后**逐文件串行**调用现有 `POST /api/documents`（`backend/app/api/documents.py:27`），原因见父 design「关键取舍 1」。后端只在该端点内加校验。
- 上传触发点仍为单文件表单/接口；前端把"一次选多份"翻译为多个受管的上传任务。

## 后端改动

### 数据层（`models/document.py` + 迁移）
- `Document` 增加 `content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=...)`；迁移 add column + **部分唯一索引** `ix_documents_user_content_hash ON documents(user_id, content_hash) WHERE content_hash IS NOT NULL`（防御并发双传）。
- `DOCUMENT_STATUSES` 增加 `"no_text"`（`String(16)` 足够）。

### 上传端点 `upload_document`（单点强化，按序）
1. `data = await file.read()` → 空校验（不变，`EMPTY_FILE`）。
2. 大小 ≤ 20MB（不变，`FILE_TOO_LARGE` 413）。
3. 文件名规范化：`filename = (file.filename or "").replace("\\","/").split("/")[-1]`；拒绝控制字符与 `<>:"/\\|?*`；`strip().strip(".")`；`len not in 1..255` → `INVALID_FILENAME`(400)；扩展名白名单（`.txt/.md/.markdown/.pdf`）→ `BAD_FILE_TYPE`(400)。
4. `content_hash = hashlib.sha256(data).hexdigest()`。
5. 判重：`select Document.id, Document.filename where user_id==当前 && content_hash==hash` 命中 → `AppError("DUPLICATE_DOCUMENT","内容已存在，原文件：<已有文件名>",409)`。（存量 NULL 哈希不受影响。）
6. PDF 图片型预检：若扩展名为 pdf，`extract_text(filename,data)`（复用 `chunking.py:22`）为空 → `status="no_text"`，`chunk_count=0`，**不创建 ingest Task**；否则 `status="uploaded"` 照旧入队。
7. 落库（含 content_hash）→ `put_object` → 非 `no_text` 时建 Task → commit。

### 序列化（`schemas/document.py` + `frontend/src/api/schemas.ts`）
- `DocumentOut` 加 `content_hash: str | None`；前端 `DocumentSchema` 对应加 `content_hash: z.string().nullable()`。

## 前端改动（`DocumentsPage.tsx`）

- input 改 `multiple`；维护 `files: {file: File; status: 'pending'|'uploading'|'ok'|'error'; message?: string}[]` 任务数组。
- 预检（选完即跑，不进网络）：
  - 扩展名白名单、大小 ≤20MB、文件名规则（镜像后端同款）；
  - 批内哈希判重（同内容文件多选，先选为准）：
    - 计算方式 `crypto.subtle.digest("SHA-256", await file.arrayBuffer())` → hex；
    - 与 `docs` 中 `content_hash` 非空项比对 → 标记「内容已存在：<name>」；
    - 与批内已算 hash 项比对 → 标记「与同批 X 重复」。
- 「上传」触发对 pending 项**逐文件串行** `postForm('/documents',…)`：成功 → `ok` 并入列表头部；失败（捕获 ApiRequestError.message，含 DUPLICATE_DOCUMENT 等）→ 该项 `error` 展示原因。不上传 error 项。
- 结果面板内联列出每项 文件名+状态徽标/原因（不再裸 `alert`，删掉 `upload()` 里的 alert 与单文件逻辑）。
- `STATUS_META` 增加 `no_text`：label「不可检索」，variant `muted`；说明文案补充"纯图片 PDF 仅预览、不可检索"。
- PENDING 轮询、删除逻辑不变。

## 明确不做

- 多文件后端端点、拖拽、进度条、断点续传、OCR。

## 风险

- 前端哈希：大文件 `arrayBuffer` 一次读入内存（≤20MB 可接受）；预检与后端哈希算法需一致（hex lowercase SHA-256，标准实现两边一致）。
- 并发双传同一内容：后端部分唯一索引兜底，命中抛 DB IntegrityError → 需 catch 转 DUPLICATE_DOCUMENT（捕获 `sqlalchemy.exc.IntegrityError` 于该列索引）。
