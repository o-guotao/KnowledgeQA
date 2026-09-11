# CHANGELOG

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 SemVer（v主.次.修订）。

## 版本策略

- **版本号**：SemVer；单一来源为根目录 `VERSION` 文件，前后端保持一致（后端直接读取，前端经 `/api/meta/version` 展示；`frontend/package.json` 发版时同步 bump）
- **分支**：main + 临时 feature/hotfix 分支，发布点合并回 main
- **Tag**：每个发布点打带注释 tag（如 `v0.2.0`）
- **CHANGELOG**：每次发版更新本文件（发版内容取自该迭代 commit 记录）
- **数据库**：迁移脚本按版本演进，发版说明中标注所属版本；既有迁移保持 0001-0013 顺序编号不变（已部署环境禁止重排 revision）

## [0.2.0] - 2026-09-11

### 新增

- 文档增量更新与失效检测：内容版本号、就地更新（`POST /documents/{id}/content`）、stale 失效检测与一键刷新（`POST /documents/{id}/reingest`）；前端版本徽标与更新入口；迁移 `0012`（83087f0）
- BM25 关键词召回接入混合检索：jieba 分词 + rank_bm25 内存索引，RRF 融合，`BM25_ENABLED` 开关，依赖缺失/异常自动回退 tsvector/LIKE（38281d1）
- 知识库团队空间：`documents.visibility=team` 全员可检索/预览，`GET /documents/team`，向量/关键词/BM25 三路召回团队可见，owner/admin 管理，前端「我的/团队空间」Tab（d274d35，迁移 `0013`）
- 版本与迭代展示：根 `VERSION` 单一来源，`GET /api/meta/version` 与 `GET /api/meta/changelog`，前端更新日志页
- ui-ux-pro-max 技能包及锁文件入库（06b4ec9）

### 变更

- `requirements.txt` 逐包标注作用与使用位置；新增 jieba / rank-bm25 依赖（6b6f141、38281d1）
- BM25 指纹扩展覆盖团队空间 share/unshare 变更（懒重建）（d274d35）

## [0.1.0] - 2026-09-09

### 新增

- 初始可用版本：JWT 鉴权（HttpOnly Cookie）、SSE 流式问答、RAG（pgvector 向量 + 混合检索 + 重排）、语义/窗口切分（父子块）
- 文档管理：批量上传校验、文件夹/标签、预览、批量删除
- 答案反馈（点赞/点踩 + 看板）、管理后台（用户 CRUD/用量/成本报表）
- SQLite 本地演示模式（deploy_profile=local）、HTTPS（nginx + certbot）、数据备份与恢复（pg_dump + MinIO 快照）
- embedding 抽象化（fastembed/OpenAI/sentence-transformers/hash）与生产 fail-fast 校验、Langfuse 追踪集成
