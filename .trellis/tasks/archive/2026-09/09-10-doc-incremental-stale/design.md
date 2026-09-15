# 文档增量更新与失效检测 — 技术设计

## 结论先行

- `stale` **不落库**：它是"文档入库时配置快照（`ingest_signature`）vs 当前 settings"的纯函数，API 层读取时计算，永不过时、无需清扫任务。
- 就地更新**复用现有 ingest 链路**：更新内容 = 换对象字节 + 入队同一个 `ingest_document` 任务；worker 已有的"先删旧块再写新块"重放幂等天然支持 chunks 替换。
- 只新增 2 个端点 + 3 个文档列，不引入新组件、不改任务状态机。

## 后端改动

### 数据层

`models/document.py` 新增 3 列：

| 列 | 类型 | 说明 |
|---|---|---|
| `version` | `Integer`, default 1 | 内容版本号，仅内容变更时 +1（reingest 不加） |
| `ingest_signature` | `String(128)`, default `""` | 最近成功入库配置快照：`{chunk_strategy}\|{chunk_size}\|{chunk_overlap}\|{embedding_backend}\|{embedding_model}` |
| `ingested_at` | `DateTime(tz)`, nullable | 最近成功入库时间 |

迁移 `alembic/versions/0012_document_version_ingest.py`（down_revision=`0011_usage_records`）：
- `add_column` × 3（`version`/`ingest_signature` 带 `server_default`，sqlite/pg 均兼容 `add_column`）。
- 数据回填：`status='ready'` 的历史行按"上传时已存的 chunk_size/chunk_overlap + 当前 env 的 strategy/backend/model"拼签名（`os.getenv` 默认值与 `Settings` 默认一致）。回填后历史文档不会误报 stale，除非配置真已漂移。
- sqlite 开发模式走 `create_all`；**存量 sqlite 文件不会自动加列**（create_all 不 ALTER），与既往列新增一致——开发库删文件重建即可，README 已约定 sqlite 为演示模式。

### 失效检测服务

新建 `app/services/doc_sync.py`：

```python
def current_ingest_signature(settings) -> str
def signature_of(document, settings) -> str        # 按文档快照列拼
def stale_reasons(document, settings) -> list[str] # status != "ready" 或签名空 -> []
def is_stale(document, settings) -> bool
```

`stale_reasons` 逐段比对生成可读原因，如：
- `切分策略已变更（window → semantic）`
- `切块参数已变更（512/64 → 256/32）`
- `Embedding 已变更（fastembed/BAAI/bge-small-zh-v1.5 → openai/text-embedding-3-small）`

### worker（`worker/main.py`）

`ingest_document` 成功收尾处（现 `document.status = "ready"` 附近）追加：

```python
document.ingest_signature = current_ingest_signature(settings)
document.ingested_at = datetime.now(timezone.utc)
```

失败路径不写签名（保持上次成功值），任务类型不变。

### API（`api/documents.py`）

**`POST /documents/{id}/content`**（multipart `file`）：
1. 属主校验 → 404。
2. `status in ("uploaded","processing")` → 409 `DOCUMENT_PROCESSING`（避免与在途 ingest 竞争）。
3. 复用上传校验管线 1-4、6 步（非空/大小/文件名/扩展名/PDF 探测，错误码一致）。
4. `sha256` 比对：
   - 等于本文档 `content_hash` → 200 `{updated: false, document}`（幂等 no-op）。
   - 等于其他文档（`user_id` 同、`id` 不同）→ 409 `DUPLICATE_DOCUMENT`（预查 + 唯一索引兜底）。
5. 写新对象（新 key 含新文件名）→ 更新行（`filename`/`object_key`/`content_hash`/`version+=1`/状态）→ 删旧对象（best-effort，与 delete 一致）。
6. 结果状态：
   - 有文字 → `uploaded` + 入队 `ingest_document`（payload 不变，worker 重放会清旧块）。
   - `no_text` → **同事务内联** `DELETE FROM chunks WHERE document_id=...`、`chunk_count=0`，不入队。

**`POST /documents/{id}/reingest`**：
- 404 属主校验；`no_text` → 400 `NOT_INGESTABLE`；处理中 → 409。
- 置 `uploaded` + 入队 `ingest_document`，version 不变。

**stale 透出**：`GET /documents`、`GET /documents/{id}` 序列化时计算 `stale`/`stale_reasons`。抽 `_to_out(document, settings) -> DocumentOut` 供各端点复用。

### schemas（`schemas/document.py`）

- `DocumentOut` += `version: int`、`stale: bool`、`stale_reasons: list[str]`、`ingested_at: datetime | None`。`stale*` 不进 ORM，构造时传入（`model_validate` 改为手工构造或 `model_construct`，实现时定）。
- 新增 `ContentUpdateResult {updated: bool, document: DocumentOut}`。

## 前端改动

- `api/schemas.ts`：`DocumentSchema` += `version`、`stale`、`stale_reasons`、`ingested_at`。
- `api/client.ts`：无需新封装（`postForm`/`post` 够用）。
- `pages/DocumentsPage.tsx`：
  - 行内徽标区：stale → 警示色 `需刷新` 徽标（`title={stale_reasons.join("\n")}`）；文件名旁加 `v{version}` 小字。
  - 操作区加两个 icon 按钮：
    - `RefreshCw` 一键刷新（`stale || status==="failed"` 时显示）→ `POST /documents/{id}/reingest` → 复用现有轮询。
    - `FileUp` 更新内容 → 隐藏 file input → `postForm /documents/{id}/content` → `updated=false` 时 toast"内容未变化"。
  - 复用现有 `PENDING_STATUSES` 轮询，更新后状态自然流转。

## 明确不做

- 定时自动重同步、版本历史/回滚、diff 视图、通知推送。
- `GET /documents/stale` 独立端点（列表已带计算字段，YAGNI）。

## 风险与决策

| 风险 | 决策 |
|---|---|
| 更新内容与在途 ingest 竞争（worker 已读旧字节） | 处理中一律 409，调用方稍后重试 |
| 历史行签名缺失误报 stale | 迁移按 env 回填 ready 行；签名空 → 不判 stale 双保险 |
| ready → no_text 更新后旧块残留被召回 | content 端点内联删 chunks（同一事务） |
| 更新后至重切完成前，召回短暂命中旧内容 | 可接受：`status=processing` 透出，worker 删+写同一事务，无半更新态 |
| 唯一索引兜底 | `IntegrityError` → 409，与上传端点同一模式 |
