# 文档增量更新与失效检测

## Goal

知识库文档当前只能"上传新文件 / 删除旧文件"，内容更新必须删了重传（chunks、文档 id、引用全部失效）；且 chunk 参数 / embedding 模型调整后，已入库文档静默过期无人知晓。本任务实现：

1. **文档版本号 + 就地更新**：对已有文档上传新内容，hash 比对后替换文件并重新切分，版本号 +1，文档 id 不变。
2. **失效检测**：识别因切分参数 / 切分策略 / embedding 配置漂移而过期的文档，列表接口透出 `stale` 标记与原因。
3. **变更通知（前端）**：文档列表展示 stale 徽标 / 版本号，提供一键刷新（重新切分）与更新内容入口。

明确不做（用户已确认）：**定时重新同步**（worker 周期扫描自动重切）不在本期范围。

## Requirements

### 后端

1. **版本字段**：`documents` 新增 `version`（默认 1）、`ingest_signature`（最近一次成功入库时的切分/embedding 配置快照）、`ingested_at`（最近成功入库时间）。postgres 走 alembic 迁移，sqlite 走 `create_all`。
2. **就地更新接口** `POST /documents/{id}/content`（multipart 文件）：
   - 复用上传校验管线（非空 / 20MB / 文件名校验 / 扩展名 / PDF 可解析性探测）。
   - 新内容 hash 与本文档当前 hash 相同 → 幂等 no-op（`updated=false`，版本不变，不入队）。
   - 新内容 hash 与**其他**文档相同 → 409 `DUPLICATE_DOCUMENT`。
   - hash 不同 → 写入新对象、更新 `content_hash`/`filename`/`object_key`、`version+1`、入队 `ingest_document` 任务。
   - 文档处理中（`uploaded`/`processing`）→ 409 拒绝，避免与运行中的 ingest 竞争。
   - 更新结果为纯图片 PDF（`no_text`）→ 不入队，同时内联清空旧 chunks（原内容块必须立即失效）。
3. **重新切分接口** `POST /documents/{id}/reingest`：用当前 settings 对**已存储内容**重新切分（stale 文档一键刷新 + failed 文档重试共用此路径）。`no_text` → 400；处理中 → 409。
4. **失效检测**：worker 每次 ingest 成功时写入 `ingest_signature`（切分策略 + chunk_size + chunk_overlap + embedding 后端/模型）。`GET /documents` 与 `GET /documents/{id}` 返回计算字段 `stale` / `stale_reasons`（仅 `ready` 文档参与判定；签名未记录的历史文档不判 stale）。stale 不落库——它是"文档快照 vs 当前 settings"的纯函数。
5. **schema**：`DocumentOut` 增加 `version` / `stale` / `stale_reasons` / `ingested_at`；content 更新响应含 `updated` 标志。

### 前端

6. `DocumentSchema` 同步新增字段。
7. DocumentsPage：
   - stale 文档显示警示徽标（hover 展示原因）与 `v{n}` 版本号。
   - 一键刷新按钮（stale 或 failed 时可见）→ 调 reingest → 复用现有轮询刷新状态。
   - "更新内容"入口（选择本地文件 → 调 content 接口 → 提示已更新/内容未变化）。

## Acceptance Criteria

- [ ] 对已有文档上传**不同内容**：`version` +1、旧 chunks 被替换、文档 id 不变、问答召回基于新内容。
- [ ] 上传**相同内容**到同一文档：返回 `updated=false`，不产生任务、版本不变。
- [ ] 上传与**另一文档**相同的内容：409 `DUPLICATE_DOCUMENT`。
- [ ] 处理中的文档调 content/reingest：409。
- [ ] 修改 `CHUNK_SIZE`（或 embedding 模型）后重启，`GET /documents` 中已 ready 文档 `stale=true` 且原因可读；调 reingest 后 `stale=false`。
- [ ] ready 文档更新为纯图片 PDF：status=no_text，旧 chunks 被清空（召回不再命中）。
- [ ] 前端列表展示 stale 徽标/版本号，一键刷新后徽标消失。
- [ ] postgres 迁移 upgrade/downgrade 通过；sqlite 模式 `create_all` 正常。

## Out of Scope

- 定时重新同步（worker 周期扫描 stale 自动重切）。
- 变更通知推送（站内信/邮件）、文档 diff 视图、版本历史保留与回滚（旧版本对象随更新即删除）。
- 多模态 / OCR。

## Notes

- 遵循"无新组件优先"：全部在现有 FastAPI + worker + Postgres/MinIO 内实现。
- 规范参考：`.trellis/spec/backend/documents-api.md`（上传管线顺序、判重、对象键约定）。
