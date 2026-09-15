# 方案 A：EdgeOne Pages 托管前端 + 后端留 CVM（混合部署）

> 架构：前端静态资源交给 EdgeOne Pages（全球边缘加速），后端 FastAPI/worker/Postgres/MinIO 继续跑在云服务器 CVM 的 `docker-compose`；API 由 EdgeOne 反代到 CVM 源站。保留本地 embedding、常驻 worker、SSE 完整能力，前端改动几乎为零。

```
浏览器
  │  https://qa.example.com            （EdgeOne Pages，静态托管 + CDN）
  ├─ /            → EdgeOne Pages 静态资源（React 构建产物 dist/）
  └─ /api/*       → EdgeOne 回源/规则引擎 → http(s)://<CVM>:8000（FastAPI，docker-compose）
                                                ├─ Postgres+pgvector（容器）
                                                ├─ MinIO（容器）
                                                └─ worker（容器，本地 fastembed embedding）
```

---

## 一、前端部署到 EdgeOne Pages

1. EdgeOne 控制台 → **Pages** → 创建项目，连接 Git 仓库（或直接上传构建产物）。
2. 构建配置：
   - 框架预设：**Vite**
   - 根目录：`frontend`
   - 构建命令：`npm run build`
   - 输出目录：`dist`
   - Node 版本：`20`
3. 环境变量（Pages 项目设置 → 环境变量）：
   - **对接方式一（推荐，同源反代）**：`VITE_API_BASE_URL` **留空** → 前端用相对路径 `/api`，由 EdgeOne 把 `/api` 反代到后端（见第二节），同源免 CORS。
   - **对接方式二（直连后端子域名）**：`VITE_API_BASE_URL = https://api.example.com` → 前端直连后端绝对地址，此时后端 CORS 必须放行前端 Pages 域名（见第三节）。
4. 触发部署，得到 Pages 默认域名 `xxx.edgeone.app`（或绑定自定义域名 `qa.example.com` 并配置 HTTPS 证书）。

> 前端代码已支持 `VITE_API_BASE_URL`（`src/api/client.ts` 的 `API_BASE`）：留空走相对 `/api`，填值走绝对地址。本地 dev 仍由 `vite.config.ts` 的 proxy 把 `/api` 转 `localhost:8000`，不受影响。

---

## 二、EdgeOne 反代 `/api` 到 CVM 源站（对接方式一）

目标：`https://qa.example.com/api/*` → `http(s)://<CVM_IP>:8000/api/*`。

1. EdgeOne 控制台 → 站点 → **规则引擎**（或「源站」/「负载均衡」）：
   - 新增源站：后端 CVM，地址 `<CVM_IP>:8000`，回源协议按需（见第三步 HTTPS）。
   - 新增规则：匹配 `路径 /api/*` → 回源到该源站；其余路径 → Pages 静态资源。
2. **SSE 流式必须的两项**（否则打字机会整段缓冲后一次性返回）：
   - 对 `/api/*` **关闭缓存**（Cache 设为不缓存 / Bypass）。
   - 关闭**响应缓冲 / 开启分块透传**（若控制台有「分块传输」「流式」开关则打开），并把**回源读超时**调大（建议 ≥ 120s，覆盖长回答）。
3. 若 Pages 项目与加速域名分离，确保 `/api` 规则优先级高于静态资源匹配。

> 说明：EdgeOne 边缘节点对长连接 SSE 的支持以「不缓存 + 长超时 + 分块透传」为前提；配置后务必实测一次流式回答确认逐 token 到达。

---

## 三、CVM 后端部署（docker-compose）

1. 按 `docs/deploy-vm.md` 用 `docker compose up -d --build` 启动全套（backend/worker/db/minio）。
2. **CORS**（仅对接方式二需要）：根 `.env` 的 `CORS_ORIGINS` 追加前端域名，逗号分隔：
   ```ini
   CORS_ORIGINS=http://localhost:5173,https://qa.example.com,https://xxx.edgeone.app
   ```
   对接方式一（同源反代）无需改 CORS。
3. **HTTPS / 回源协议**：
   - 推荐 EdgeOne 回源用 **HTTPS**：后端经 nginx（compose 的 `nginx` profile）配证书监听 443，源站填 `443`。
   - 若暂用 HTTP 回源，源站填 `80`/`8000`，但公网明文仅限测试。
4. **防火墙 / 安全组**：仅放行 EdgeOne 回源 IP 段（或 80/443），不要把 `8000` 直接对公网全开放。
5. **密钥**：`DEEPSEEK_API_KEY`、`MODEL_CONFIG_ENCRYPTION_KEY` 等只放 CVM 的 `.env`（前端零密钥，已由架构保证）。

---

## 四、两种对接方式对比

| | 方式一：同源反代（推荐） | 方式二：直连子域名 |
| --- | --- | --- |
| 前端 `VITE_API_BASE_URL` | 留空 | `https://api.example.com` |
| API 入口 | `qa.example.com/api`（EdgeOne 反代） | `api.example.com`（CVM 直连） |
| CORS | 无需（同源） | 后端需放行前端域名 |
| DNS | 一个域名 | 需 `qa.*` + `api.*` 两个 |
| 适用 | 统一入口、最省心 | 前后端域名分离、后端独立加速 |

---

## 五、上线检查清单

- [ ] Pages 构建成功，`https://qa.example.com` 打开前端（深炭黑主题）。
- [ ] `https://qa.example.com/api/healthz`（方式一）或 `https://api.example.com/api/healthz`（方式二）返回 `{"status":"ok"}`。
- [ ] 登录 `demo/demo1234` 成功（验证 API 连通）。
- [ ] 发起一次对话，确认 **SSE 逐 token 打字机**（若整段一次性返回 → 回源缓存/缓冲未关）。
- [ ] 上传文档 → worker 切分入库 → 问答可引用（验证后端 + embedding + 存储链路）。
- [ ] 配额/用量在管理后台可见（验证数据库与明细写入）。

---

## 六、注意事项

- **本地 embedding 保留**：worker 仍在 CVM 容器内跑 fastembed 本地 BGE，无需云端 embedding key，这是方案 A 相对全栈 EdgeOne 的核心优势。
- **回源超时**：EdgeOne 默认回源超时可能偏短，SSE 长回答需调大；否则流会被中途截断。
- **不要在 Pages 端缓存 `/api`**：会导致 SSE 失效与数据过期。
- **切换/回退**：改 `VITE_API_BASE_URL` 即可在两种对接方式间切换；回退到纯 CVM 部署时前端也用相对 `/api`（nginx 反代），无需改代码。
