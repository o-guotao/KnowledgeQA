# KnowledgeQA 腾讯云部署手册（Runbook）

> 架构：EdgeOne CDN（边缘 HTTPS）→ CVM `docker compose` 一体化后端（FastAPI + worker + Postgres + MinIO + 本地 fastembed embedding）。
> 分两阶段：**阶段一（域名备案审批中）用 CVM 公网 IP 跑通全栈；阶段二（备案完成）接 EdgeOne CDN 上 HTTPS**。两阶段用同一套 `nginx-cdn` 配置，无缝切换。

```
阶段一（现在）：浏览器 → http://<CVM_IP>:80 (nginx-cdn) → / frontend:80 · /api backend:8000
阶段二（备案后）：浏览器 → https://qa.域名 (EdgeOne CDN) → 回源 http://<CVM_IP>:80 (nginx-cdn) → 同上
```

---

## 0. 前置条件

| 项 | 要求 |
| --- | --- |
| CVM | 轻量应用服务器，建议 4核8G；2核/4核 4G 也可（须加 Swap，见下） |
| 防火墙 | 放行 `22`(SSH)、`80`；**不**开 `8000/9000/5432` |
| 代码 | 本地已 `git push` 到远端（`.env` 已 gitignore，不含密钥） |
| 域名 | 阶段一不需要；阶段二需已备案 |

---

## 阶段一：CVM 公网 IP 跑通全栈（备案审批中）

### 1.1 初始化（SSH 登录 CVM）
```bash
# 装 Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER && newgrp docker
docker -v && docker compose version

# 加 Swap（4GB 内存必做，防 worker 切分 OOM）
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # 应见 Swap 4.0G
```

### 1.2 拉代码 + 配 .env
```bash
git clone <仓库地址> web-agent && cd web-agent
cp .env.example .env
# 生成两个密钥（CVM 自带 python3）
python3 -c "import os,base64; print('MODEL_CONFIG_ENCRYPTION_KEY='+base64.urlsafe_b64encode(os.urandom(32)).decode())"
python3 -c "import secrets; print('JWT_SECRET='+secrets.token_urlsafe(48))"
nano .env
```
`.env` 填入：
```ini
DEPLOY_PROFILE=production
POSTGRES_PASSWORD=<强密码>
MINIO_ROOT_PASSWORD=<强密码>
JWT_SECRET=<上面生成>
MODEL_CONFIG_ENCRYPTION_KEY=<上面生成>
DEEPSEEK_API_KEY=sk-<真实 key>
CORS_ORIGINS=http://<CVM_IP>
OMP_NUM_THREADS=2
```

### 1.3 启动（一条命令，自动按依赖顺序）
```bash
docker compose --profile cdn up -d --build
```
启动顺序（compose 自动编排）：`db + minio`(先健康) → `minio-init`(建 bucket) → `backend`(迁移+seed+uvicorn) → `worker` → `frontend` → `nginx-cdn`。

> ⏳ 首次较慢：backend 镜像装 Python 依赖 + worker 首次下载 BGE 模型（~100MB 到 `modelcache` volume）。耐心等 3-10 分钟，用 `docker compose logs -f backend` / `-f worker` 观察。

### 1.4 阶段一验证清单
- [ ] `docker compose ps` 全部 `healthy`/`running`
- [ ] `curl http://127.0.0.1/api/healthz` → `{"status":"ok"}`（本机经 nginx-cdn）
- [ ] `curl http://<CVM_IP>/api/healthz` → `{"status":"ok"}`（公网经防火墙 80）
- [ ] `docker compose logs worker | grep -i fastembed` → 加载成功（**不应**是 `downgraded to hash`；若是则 embedding 无语义，查内存/模型下载）
- [ ] 浏览器 `http://<CVM_IP>` 打开前端（深炭黑主题），登录 `demo/demo1234`
- [ ] 发起对话：**SSE 逐 token 打字机**（若整段一次性返回 → nginx 缓冲未关，查 `nginx.cdn.conf`）
- [ ] 上传一份文档 → `docker compose logs -f worker` 见切分/向量化 → 状态变「已入库」→ 问答能带引用
- [ ] 侧栏「管理后台」（demo 是 admin）→ 用户/用量可见

> 纯 IP 为 HTTP（无证书），仅临时测试；`8000/9000/5432` 全程不对公网开放。

---

## 阶段二：备案完成后接 EdgeOne CDN（上 HTTPS）

> **无需改 CVM 任何东西**（沿用阶段一的 nginx-cdn）。

### 2.1 DNS
- `qa.你的域名` → CNAME 到 EdgeOne 分配的 CNAME 地址

### 2.2 EdgeOne 站点加速
1. 控制台 → 站点加速 → 添加站点 → **CNAME 接入** `qa.你的域名`
2. 边缘 **HTTPS**：申请免费证书（域名已备案，自动签发）
3. **回源**：源站协议 **HTTP**、地址 `<CVM_IP>:80`
4. **缓存规则**：
   - `/api/*` → **不缓存** + 分块透传（SSE 关键）
   - 静态资源（`/`、`/assets/*`）→ 可缓存
5. CORS：前端与 API 同源（`qa.你的域名/api`），无需设

### 2.3 阶段二验证清单
- [ ] `curl https://qa.你的域名/api/healthz` → `{"status":"ok"}`（经 CDN→CVM→backend）
- [ ] 浏览器 `https://qa.你的域名` 登录，**SSE 逐 token**（整段返回 = CDN 缓存/缓冲未关）
- [ ] 上传→引用链路复测一遍

---

## 3. 日常运维

```bash
docker compose logs -f backend     # 后端日志
docker compose logs -f worker      # worker/embedding 日志
docker compose restart backend     # 重启某服务
docker compose --profile cdn up -d --build   # 代码更新后重建
docker compose down                # 停止（数据保留在 volume）
```
- 更新代码：`git pull && docker compose --profile cdn up -d --build`
- 备份：见 `docs/backup-restore.md`（pg_dump + MinIO 数据 + certbot 证书）

## 4. 故障排查

| 现象 | 排查 |
| --- | --- |
| SSE 整段一次性返回 | nginx/CDN 缓冲未关：查 `nginx.cdn.conf` 的 `proxy_buffering off`、CDN 的 `/api` 不缓存+分块透传 |
| worker 日志 `downgraded to hash` | embedding 无语义：查内存是否够（4G 须 Swap）、BGE 模型是否下载成功（`modelcache` volume） |
| `docker compose ps` worker 重启/OOM | 内存不足：确认 Swap 生效、worker `mem_limit:1536m`、omp 线程=2 |
| 502 Bad Gateway | backend 未 healthy：`docker compose logs backend`；nginx-cdn 起来了但 backend 没就绪 |
| 对话 401 | `DEEPSEEK_API_KEY` 未配/无效（服务端 .env） |
| 上传 413 | 文件 >20MB 或 nginx `client_max_body_size` 太小（已配 25m） |
| `api/healthz` 通但前端打不开 | frontend 容器未起（`docker compose ps frontend`）或 nginx-cdn 配置未生效 |

---

## 附：部署架构与配置索引
- compose：`docker-compose.yml`（profile `cdn` = nginx-cdn 回源反代；profile `edgeone` = 443 域名方案备用）
- nginx：`deploy/nginx/nginx.cdn.conf`（CDN/IP 回源反代）、`nginx.edgeone.conf`（443 域名方案）
- 前端 API base：`frontend/src/api/client.ts` 的 `VITE_API_BASE_URL`（默认空=相对 /api 同源）
- 详细方案：`docs/deploy-tencent-cloud.md`（含预算）、`docs/deploy-edgeone.md`
