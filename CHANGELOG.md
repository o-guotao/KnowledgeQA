# CHANGELOG

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 SemVer（v主.次.修订）。

## 版本策略

- **版本号**：SemVer；单一来源为根目录 `VERSION` 文件，前后端保持一致（后端直接读取，前端经 `/api/meta/version` 展示；`frontend/package.json` 发版时同步 bump）
- **分支**：main + 临时 feature/hotfix 分支，发布点合并回 main
- **Tag**：每个发布点打带注释 tag（如 `v0.2.0`）
- **CHANGELOG**：每次发版更新本文件（发版内容取自该迭代 commit 记录）
- **数据库**：迁移脚本按版本演进，发版说明中标注所属版本；既有迁移保持 0001-0013 顺序编号不变（已部署环境禁止重排 revision）

## [0.3.0] - 2026-09-14

### 新增

- **RAG 评测中心**（Admin 专属）：数据集版本化（内置样例/上传 jsonl）、worker 异步评测运行（4 组配置矩阵 baseline/hybrid/+BM25/+rerank、top_k 扫描、分阶段计时）、可选 LLM 答案正确率（gold_keywords 命中，provider 与日常问答同源）、可视化（配置组柱状 / Recall@K 曲线 / 逐题明细 / 指标对比表 / 线上延迟趋势）、运行删除与批量删除；迁移 `0014`（4a141cb、3da08d6、2a14b2b、a1f35b9）
- **评测语料模式**：sample（内置样例文档）/ online（创建者线上知识库，检索范围=本人+团队空间），修复自定义数据集 gold_doc 与固定样例语料不匹配导致召回全 0 的问题（3da08d6）
- **线上分阶段耗时采集**：chat 链路记录 ttft/total/recall/rerank 至 `usage_records`，`/admin/eval/online-stats` 按日 p50/p95 + 点踩率（4a141cb）
- ICP 备案号全站页脚（链接工信部备案官网），备案号支持 `VITE_ICP_NUMBER` 构建期覆盖（a1de78c）
- HTTPS 部署支持主域名 + www 双域名（nginx `EXTRA_DOMAINS`、certbot 多域名签发）（697178f）

### 变更

- 评测中心交互：勾选驱动面板（1 个看明细 / 2 个进入对比 / 更多仅批量管理），对比视图重做为「同组跨 run 曲线 + 双列明细 + 精确指标表」（2a14b2b）
- Admin 页面容器加宽至 1400px；评测列表状态改紧凑圆点、配置组缩写、单元格禁换行（8835508）

### 修复

- 评测 `with_llm` 的 provider 与日常问答同源（模型设置优先，全局 DeepSeek 兜底），修复 `.env` 占位 key 导致的 401（51b5b54）
- 评测 `with_llm` 逐题容错 + 组内降级，LLM 失败不再搞挂整个 run（4a141cb）
- 新评测 run 完成后图表自动切换；评测运行全部行可点击查看详情（036ae94、7121a5d）
- 评测运行删除显式清理逐题明细（sqlite 默认不强制 FK CASCADE）（a1f35b9）

### 文档

- 新增 `docs/检索融合与排序机制.md`：链路与参数、RRF 等权设计、重排覆盖机制、BM25 jieba 分词细节、实测效果与调优建议、加权融合改造方案（47a4470）

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
