# CHANGELOG

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 SemVer（v主.次.修订）。

## 版本策略

- **版本号**：SemVer；单一来源为根目录 `VERSION` 文件，前后端保持一致（后端直接读取，前端经 `/api/meta/version` 展示；`frontend/package.json` 发版时同步 bump）
- **分支**：main + 临时 feature/hotfix 分支，发布点合并回 main
- **Tag**：每个发布点打带注释 tag（如 `v0.2.0`）
- **CHANGELOG**：每次发版更新本文件（发版内容取自该迭代 commit 记录）
- **数据库**：迁移脚本按版本演进，发版说明中标注所属版本；既有迁移保持 0001-0013 顺序编号不变（已部署环境禁止重排 revision）

## [未发布]

### 新增

- **门面首页（/）：滚动叙事作品集 React+TS 重写**：原 `public/showcase` 静态页（865 行 JS + 881 行 CSS）
  等价移植为 `src/showcase/`（showcaseMath 纯函数 + useScrollProgress/useIntroScrub 引擎 + 10 个组件），
  保留全部交互纪律（不从 currentTime 读回控制量 / 值没变不写 DOM / seek 挂起 / reduced-motion 与触屏降级）；
  高频进度值 ref 直写不进 React state
- **作品预览节接入真实应用**：iframe 实时内嵌 `/app`（未登录显示登录页，所见即所得）+ 三张可点卡片
  （RAG 卡跳 `/app`，网站/Agent 卡占位）；文件夹内页改真 DOM 三卡片（可选中文字 + card-rag/web/agent.png）
- **无视频叙事降级**：main.mp4 缺失时按节内进度写 `--par` 视差变量呈现，视频接口保留（放入
  `public/media/main.mp4` 即自动接管）；媒体素材迁至 `public/media`，静态 showcase 已删除
- **top_k 按问题复杂度自适应（L1-L3）**：L1 前端「检索范围」改为四档语义按钮（自动/精确 3/均衡 5/广泛 10），
  默认自动；L2 后端规则路由 `auto_top_k`（列举/对比类 → 10、单点事实短问句 → 3、其余 → 5）；
  L3 重排后分数断崖截断（top_k 退化为上限，证据集中时实际块数更少，下限 3，仅自动模式且重排开启时生效，
  用户显式指定 top_k 时不截断）。L4（LLM 查询分类路由）未做，见 `docs/功能规划.md`
- CORS methods/headers 收紧为显式列表（带凭证跨域规范）
- **门面叙事视频**：`intro-loop.mp4`（首屏擦洗）与 `main.mp4`（滚动叙事）均经 delogo 去水印 +
  lanczos 升采样至 2560×1440 + 密关键帧（GOP=6，保证 seek 每帧清晰）+ CRF22 处理；fallbackDuration
  与 intro 对齐为 10，HUD 时间码不再在首屏/其余节间跳变
- **AuthLayout 公共外壳**：登录/注册页品牌区/特性列表/版本号逻辑收拢至 `components/AuthLayout.tsx`
  （此前两页整块复制约 80 行×2）

### 变更（破坏性）

- **KnowledgeQA 应用整体迁移至 `/app` 前缀**：`/login`→`/app/login`、`/`→`/app`、`/documents`→`/app/documents`、
  `/settings/models`→`/app/settings/models`、`/admin`→`/app/admin`、`/changelog`→`/app/changelog`；
  登录后默认进 `/app`；`/` 成为公开门面页；站内全部跳转点已同步更新

### 修复

- **可访问性（WCAG 2.2）**：① 768px 抽屉关闭态 `visibility:hidden` 移出 Tab 序（原焦点进入屏外元素）；
  ② 全局 `:focus-visible` 焦点环补齐裸按钮（原仅 ui/Button 等有，键盘导航隐身）；③ 点击区 <24px 统一提升
  （会话删除钮常显 26px、版本钮/引用角标/反馈钮/搜索清除钮 padding、原生 checkbox 13→18px）；
  ④ 标题层级修正（Hero 装饰字组 h2→p，首个标题恢复为 h1）；⑤ 预览弹窗补 ESC 关闭 + 图片可键盘缩放；
  ⑥ Eval 表行 `tr onClick` 补 Enter/Space 键盘可达；⑦ 会话行 div[role=button] 补 Space 键
- **对比度**：`--ink-faint` alpha .42→.62（3.1:1→4.9:1，达 AA）；ICP 备案文字 slate-500 11px→slate-400 12px
  （2.6:1→4.9:1）；首屏右栏/gaze 区换双层暗晕 text-shadow 保住视频人脸上的可读性
- **弹窗与错误反馈统一**：ModelSettings `window.confirm`→`ConfirmDialog`；Documents 5 处 `window.alert`
  →行内错误横幅（6s 自动消失）；DocumentPreviewModal 补 ESC + 白底容器内 ghost 按钮强制深色文字
- **双主题一致性**：`html.light` 兜底补 4 条（divide-slate-100 / bg-black/40 / bg-slate-950 系 /
  hover:bg-indigo-100）；Admin/ModelSettings/Eval 的浅色 banner（bg-red-50 等 7 处）+ Badge 三变体
  统一到项目惯用式 `*-500/30 + *-500/10 + *-400`（深色主题下不再有亮盒违和）
- **Admin 权限守卫**：非管理员访问 `/app/admin` 显示权限空态，不再泄露管理骨架 + 满屏报错
- **Changelog**：条目内联 Markdown 改 `react-markdown` 渲染（原 `**` 星号裸露）；补加载骨架
- **文件夹弹图**：① 收起按钮 `right:-50%`→`fixed/right:var(--gut)`（1440 裁边、768 全屏外→均在屏内）；
  ② 弹图 `max-height: calc(100vh-21rem)` 不再越出视口压 HUD、橙色标题带不再被腰斩；
  ③ 底部渐隐 16%→8%（保住文件夹标题带）；④ `place-items:start center` 上移避开视频中上部人脸 +
  为提示行留位；⑤ 弹图打开时 scrim `is-dim` 整屏压暗一档（人物退为背景）；⑥ 焦点回位延迟 320ms
  等 openbtn visibility 过渡结束（原立即 focus 被浏览器忽略，焦点丢到 body）
- **作品预览 iframe 自适应**：原 `133%+scale(.75)` 方案因 `overflow:hidden` 在 transform 之前裁剪
  导致 iframe 实际可见只剩 frame 的 75%（右下 1/4 空白透出视频）；重构为 `container-type:inline-size`
  + `aspect-ratio:16/9`（与 iframe 内部 1280×720 同比）+ `scale(calc(100cqw/1280px))`，视觉与 frame
  严丝合缝、内部 app 以桌面视口渲染自适应；静态底图由人像照片换为产品登录页截图；CTA 改实心 pill
- **预览节滚动条**：视觉隐藏（`scrollbar-width:none` + webkit `display:none`），滚动能力保留
- **首页不渲染 ICP 页脚**：App.tsx 抽 Shell 用 useLocation，`pathname === "/"` 时不渲染 IcpFooter
  （原与 HUD 矩形相交 7px）；各滚动页主容器加 `pb-14` 避免内容从固定页脚下穿过
- **登录页**：移除用户名 `demo` 开发预填
- **Documents 文件夹/标签输入**：原生 input 换 `ui/Input`（获统一 focus 环）

## [0.4.0] - 2026-09-17

### 新增

- **开放注册**：`POST /auth/register`（用户名查重 409、密码强度/长度校验 400，role 固定 user，不发 token 不写 Cookie），前端 `/register` 注册页（复用登录页视觉，含确认密码本地校验），注册成功跳回登录页展示「注册成功，请登录」；`REGISTRATION_ENABLED` 开关（local 默认开、production 默认关）
- **多模态文档**：新增图片（png/jpg/jpeg/webp）上传（仅预览不入库，复用 no_text 终态）与 docx/xlsx 上传（python-docx/openpyxl 提取段落+表格/逐 sheet 文本入库，RAG 可检索）；上传白名单、accept、提示文案、列表文件类型图标同步扩展；新依赖 python-docx、openpyxl
- **文档预览按类型分发**：图片原图 blob 预览（点击缩放）、docx 用 docx-preview 保留排版、xlsx 用 SheetJS 结构化渲染（sheet 切换 tab、表头吸顶、超 500 行截断提示）；前端新依赖 docx-preview、xlsx（均动态 import 不增主 bundle）
- **PDF 表格结构化**：PDF 提取由 pypdf 换为 pdfplumber，表格转 Markdown 管道表保留行列语义、正文排除表格区域避免重复；上传探测改轻量 `pdf_has_text`（只看前 3 页）避免大 PDF 拖慢上传；新依赖 pdfplumber
- 公安备案号页脚展示，`VITE_GA_NUMBER` 构建期覆盖

### 安全

- **注册/登录限流**：进程内滑动窗口（注册 10 次/分钟/IP、登录 20 次/分钟/IP，超限 429），防批量注册刷库、用户名枚举与口令爆破；多实例部署需换 Redis 共享存储
- **xlsx 预览 XSS 修复**：弃用 `sheet_to_html`（其 `data-v` 属性未转义，单元格含双引号可属性突破注入），改为 `sheet_to_json` + React 原生渲染
- **docx 预览禁用外部链接跳转**：渲染后移除 `<a>` href，团队文档夹带的外部链接只展示不可点击
- **用户名归一化**：注册/登录/管理员建用户统一 strip + 小写，杜绝大小写产生两个账号；注册唯一索引竞态兜底转 409

### 变更

- reingest 放开 no_text 逃生通道：pdf/docx/xlsx 的 no_text 文档允许重切（救回「前几页纯图」误判，仍无文本落 failed），图片文件仍拒绝
- 登录页/注册页页脚版本号由硬编码改为 `/api/meta/version` 动态获取

### 变更（破坏性）

- **列表接口返回形状改为分页信封**：所有列表接口（`/documents`、`/documents/team`、
  `/sessions`、`/sessions/{id}/messages`、`/model-configs`、`/admin/users`、
  `/admin/usage/by-user`、`/admin/usage/by-model`、`/admin/eval/datasets`、
  `/admin/eval/runs`、`/meta/changelog`）由裸数组改为
  `{items,total,page,page_size,pages}`，并新增 `q`（关键词）+ `page` + `page_size` 参数。
  前后端必须同版本部署；CDN 若缓存旧前端包，旧包调用新后端会报「响应数据格式异常」。
  例外（有意保留裸数组/不分页）：`/documents/folders`、`/admin/usage/daily`、
  `/admin/eval/runs/{id}` 的逐题明细、CSV 导出。

### 新增

- **全系统列表搜索与分页**：文档（我的/团队空间）、管理后台用户与用量表、评测中心数据集与运行记录、
  会话侧栏、历史消息、模型配置、更新日志均支持服务端关键词搜索与服务端分页；
  前端统一 `usePaginatedQuery` + `SearchInput` + `Pagination` 三件套。
- **`GET /documents/stats`**：文档列表顶部计数（total/ready/processing/failed/no_text），
  解决分页后「客户端全量统计」失真的问题。
- **历史消息分页**：`/sessions/{id}/messages` 支持倒序分页（page=1 为最新一页），前端
  「加载更早」向上累加，流式作答中禁用以免与乐观消息交叉。
- **会话侧栏搜索 + 加载更多**：会话列表按标题搜索，分页累加而非页码。

### 修复

- `/admin/eval/runs` 移除硬编码 `.limit(100)`：此前评测运行超过 100 条会被静默截断。
- 中文标签搜索失效：SQLite 下 `JSON` 列以 `ensure_ascii=True` 序列化（中文存为 `\uXXXX`），
  导致 `tags` 关键词搜索永不命中；新增 `json_text_search` 同时匹配原文与转义形式，方言无关。

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
