# 知识库团队空间

## Goal

当前知识库完全私有（文档/切块按 `user_id` 隔离），团队共用的制度、手册无法共享，每人重复上传。本任务实现**轻量团队空间**：文档可标记为"团队空间"，全部登录用户可检索/预览；owner/admin 管理；个人空间保持私有。不引入团队实体/成员关系/邀请制（那是 P3 细粒度权限的范畴）。

明确不做（用户已确认）：会话只读分享链接、评论。

## Requirements

### 后端

1. **可见性字段**：`documents` 新增 `visibility`（`private` 默认 / `team`）。postgres alembic 迁移，sqlite `create_all`。
2. **共享检索**：问答召回范围为「本人的全部文档 + 全员的 team 且 ready 文档」。三条召回路径一致覆盖：
   - 向量召回（pg / sqlite 两方言）
   - 数据库关键词召回（tsvector / LIKE 回退路径）
   - BM25 内存索引（索引行记录 team 标记；指纹需覆盖 share/unshare 变更以触发重建）
3. **团队空间列表** `GET /documents/team`：返回全员 team 文档（含 owner 显示名与状态），任何登录用户可访问。
4. **访问控制**：
   - `GET /documents/{id}`、`GET /documents/{id}/file`、`GET /chunks/{chunk_id}`：owner / admin / visibility=team 三者任一可访问（引用回跳必须支持团队文档）。
   - `PATCH /documents/{id}`：owner 可改 folder/tags/visibility；admin 对他人 team 文档可改 visibility（取消共享）。
   - `DELETE /documents/{id}`：owner 或 admin（admin 仅限 team 文档）。
   - 上传支持 `visibility` 表单字段，任何登录用户可把自己的文档共享到团队空间。
5. **schema**：`DocumentOut` 增加 `visibility` / `owner_name`（团队列表用，本人列表为 null）。

### 前端

6. DocumentsPage 分 Tab：**我的文档** / **团队空间**。
   - 我的文档：每行加"共享到团队空间 / 取消共享"切换；上传表单加"上传到团队空间"勾选。
   - 团队空间：只读列表（文档名/owner/状态/预览）；admin 额外有取消共享与删除按钮。
7. 问答页引用回跳对团队文档正常生效（无需 UI 改动，依赖后端 chunks 端点放宽）。

## Acceptance Criteria

- [ ] 用户 A 将文档共享到团队空间后，用户 B 的问答能召回其内容并带出引用；B 可预览原文件。
- [ ] A 取消共享后，B 的召回/预览/引用回跳立即失效（BM25 索引指纹覆盖该变更）。
- [ ] 私有文档行为不变：他人不可见、不可检索。
- [ ] 非 owner 非 admin 不能 PATCH/DELETE 他人 team 文档（403/404）；admin 可以。
- [ ] 前端 Tab 切换正常，团队列表显示 owner；共享/取消共享后列表即时刷新。
- [ ] postgres 迁移 upgrade/downgrade 通过；sqlite 模式正常。

## Out of Scope

- 会话只读分享链接、评论。
- 团队实体/多空间/成员管理/邀请、文档级 ACL（P3）。
- 团队空间内文档的编辑协作（他人始终只读）。

## Notes

- 遵循"无新组件优先"：仅一列 + 查询条件放宽，无新中间件。
- 规范参考：`.trellis/spec/backend/documents-api.md`。
- 召回链路近期改动：BM25（`bm25_index.py`）与 RRF（`rag.py`），团队空间需同步覆盖，回归重点。
