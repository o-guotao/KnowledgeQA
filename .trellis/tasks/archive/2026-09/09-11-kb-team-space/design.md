# 知识库团队空间 — 技术设计

## 结论先行

- 团队空间 = `documents.visibility` 一列（`private`|`team`），**无团队实体**。
- 召回授权收敛为一个 SQL 条件：`(Chunk.user_id == :uid) OR (Document.visibility == 'team')`，恒与 `Document.status == 'ready'` 组合；三条召回路径（向量/关键词 DB/BM25）统一套用。
- API 授权收敛为一个谓词：`可访问 = owner OR admin OR visibility == 'team'`；写操作 = owner，admin 仅对 team 文档降级管理（取消共享/删除）。

## 后端改动

### 数据层

- `models/document.py`：`visibility: Mapped[str] = mapped_column(String(16), default="private", index=True)`。
- 迁移 `0013_document_visibility.py`（down_revision=`0012_document_version_ingest`）：add_column + `server_default="private"`，历史行全部私有（安全默认）。

### 检索（`services/rag.py` / `services/bm25_index.py`）

公共条件（`rag.py` 顶部加 helper）：

```python
def _visible_to(user_id):  # Chunk + Document join 后使用
    return or_(Chunk.user_id == user_id, Document.visibility == "team")
```

- `_vector_recall`：sqlite 与 pg 两分支 `.where(...)` 中 `Chunk.user_id == user_id` → `_visible_to(user_id)`。
- `_keyword_recall_db`：原生 SQL `WHERE c.user_id = :uid` → `WHERE (c.user_id = :uid OR d.visibility = 'team')`（sqlite/pg 同语法）。
- `_bm25_recall` 回填查询：同上换 `_visible_to`。
- `bm25_index.py`：
  - `_Index` 增加 `team_flags: list[bool]`；构建查询 join `Document` 取 `visibility`。
  - `search()` 过滤：`user_ids[i] == user_id or team_flags[i]`。
  - **指纹扩展**：`(child 块数, max(created_at), team 文档的 child 块数)`——share/unshare 改变第三项即触发懒重建。

### API（`api/documents.py`）

授权 helper：

```python
def _can_read(doc, user) -> bool:   # owner / admin / team
def _can_write(doc, user) -> bool:  # owner；admin 仅当 doc.visibility == "team"
```

- 上传：新增 `visibility: str = Form("private")`，非法值 400；其余管线不变。
- `GET /documents/team`（**声明在 `/documents/{document_id}` 之前**，与 `/documents/folders` 同模式）：`visibility == "team"` 全部文档，join users 取 `display_name` 填 `owner_name`，按 created_at desc。
- `GET /documents/{id}`、`GET /documents/{id}/file`：404 语义不变，授权换 `_can_read`（他人私有文档仍 404，不泄露存在性）。
- `GET /chunks/{chunk_id}`：where 放宽为 `_can_read` 等价条件（join Document 判 owner/visibility，admin 放行）。
- `PATCH /documents/{id}`：owner 全字段；admin 非 owner 仅 `visibility`（body 含其他字段 → 403）。`DocumentUpdate` 增加 `visibility`。
- `DELETE /documents/{id}`：owner 或 (admin 且 team)。
- `DocumentOut`：`visibility: str = "private"`、`owner_name: str | None = None`（ORM 无此列，`_to_out` 默认 None，team 列表单独填充；与 stale 字段同模式）。
- 批量删除 `batch-delete`：保持 owner-only（admin 团队管理走单个 DELETE，不扩散面）。

### 召回安全边界

- `status != "ready"` 的 team 文档（处理中/失败/no_text）不进召回，与现状一致。
- 取消共享即时生效：DB 查询路径实时；BM25 靠指纹第三项触发重建（下一次查询即重建）。

## 前端改动

- `api/schemas.ts`：`DocumentSchema` += `visibility`、`owner_name`（nullable）。
- `pages/DocumentsPage.tsx`：
  - 顶部 Tab：`我的 | 团队空间`（state `tab`）；团队 Tab 数据来自 `GET /documents/team`（切 Tab 时拉取 + 复用轮询条件）。
  - 我的文档行：加 `Share2` 图标按钮切换共享（PATCH `visibility`），team 文档显示"团队"徽标。
  - 上传表单：checkbox `上传到团队空间`（提交时 form 带 `visibility=team`）。
  - 团队空间行：owner_name + 状态徽标 + 预览；`user.role === "admin"` 追加取消共享/删除按钮。
  - 需要当前用户 role：`AuthContext` 已有 user 信息（登录返回含 role，管理后台已用）。

## 明确不做

- 分享链接、评论、团队实体/成员/多空间、他人可写。

## 风险与决策

| 风险 | 决策 |
|---|---|
| share/unshare 后 BM25 索引不过期 | 指纹加 team 块数项，查询前比对触发懒重建 |
| 他人私有文档存在性泄露 | 非授权读仍 404（不区分不存在/无权），与现状一致 |
| `/documents/team` 与 `/documents/{id}` 路由冲突 | 静态路由先声明（FastAPI 按声明顺序匹配） |
| admin 权限扩散 | admin 仅对 team 文档可取消共享/删除；私有文档依然 owner-only |
| 取消共享后已在会话里的引用回跳 | `GET /chunks/{id}` 实时判定，取消后他人回跳 404，符合预期 |
