# 执行计划 — 知识库团队空间

按序执行；回滚点：步骤 1（迁移 downgrade）、步骤 5 前任意 `git checkout`。

## 1. 数据层 + 迁移

- [ ] `models/document.py`：`visibility` 列（String(16)，default "private"，index）。
- [ ] `alembic/versions/0013_document_visibility.py`：add_column（server_default "private"），down_revision=`0012_document_version_ingest`。
- 校验：迁移模块可导入、链路正确、downgrade 语句完整。

## 2. 检索层团队可见

- [ ] `rag.py`：`_visible_to()` helper；`_vector_recall`（两分支）、`_keyword_recall_db`（两条 SQL）、`_bm25_recall` 回填查询套用。
- [ ] `bm25_index.py`：`_Index.team_flags`、构建查询 join Document、search 过滤、指纹加 team 块数项。
- 校验（sqlite + hash embedding 冒烟）：
  - A 的 team 文档可被 B 向量/关键词/BM25 三路召回；A 私有文档 B 不可见。
  - A 取消共享 → B 下一次查询不再命中（含 BM25 路径，验证指纹重建）。

## 3. API

- [ ] `schemas/document.py`：`DocumentOut` += `visibility`/`owner_name`；`DocumentUpdate` += `visibility`。
- [ ] `api/documents.py`：
  - [ ] `_can_read`/`_can_write` helper。
  - [ ] 上传接受 `visibility` 表单字段（非法值 400）。
  - [ ] `GET /documents/team`（声明在 `{document_id}` 路由前）join users 填 owner_name。
  - [ ] `GET /{id}`、`GET /{id}/file`、`GET /chunks/{chunk_id}` 放宽为 `_can_read`。
  - [ ] `PATCH`：owner 全字段 / admin 仅 visibility；`DELETE`：owner 或 admin(team)。
- 校验（沿用 .tmp e2e 套路）：team 文档他人可读可预览；私有文档他人 404；非 owner 非 admin PATCH/DELETE team 文档被拒；admin 可取消共享/删除；上传带 visibility=team 落库正确。

## 4. 前端

- [ ] `api/schemas.ts`：`visibility`、`owner_name` 字段。
- [ ] `DocumentsPage.tsx`：Tab（我的/团队空间）、共享切换按钮、上传勾选团队空间、团队列表（owner 徽标 + 预览 + admin 管理按钮）。
- 校验：`npm run build` 通过；手测 Tab 切换与共享流程。

## 5. 质量检查与收尾

- [ ] `read_lints` 无新增错误。
- [ ] E2E 冒烟全绿（检索三路 + API 授权矩阵）。
- [ ] spec 更新：`.trellis/spec/backend/documents-api.md` 补 visibility 授权矩阵与团队空间端点。
- [ ] `docs/功能规划.md` 完成情况快照：P2 对话分享+团队空间行更新（团队空间✅/分享链接❌拆分标注）。

## 回滚

- 代码：`git checkout`。
- 迁移：`alembic downgrade 0012_document_version_ingest` 后删 0013 文件。
