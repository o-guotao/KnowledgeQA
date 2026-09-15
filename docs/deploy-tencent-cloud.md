# 腾讯云部署指导（EdgeOne Pages 前端 + CVM 一体化后端）与预算

> 架构：前端静态资源 → EdgeOne Pages（免费边缘加速）；后端 FastAPI/worker/Postgres/MinIO/本地 embedding → CVM 一体化 `docker-compose`；`/api` 由 EdgeOne 反代回源。保留本地 embedding，免云端模型/托管数据库费用，成本最低。

```
浏览器
 ├─ /       → EdgeOne Pages（前端 dist/，免费 CDN）
 └─ /api/*  → EdgeOne 反代 → CVM:8000（docker compose）
                                  ├─ backend (FastAPI + SSE)
                                  ├─ worker  (切分 + 本地 fastembed BGE)
                                  ├─ db      (Postgres + pgvector)
                                  └─ minio   (对象存储)
```

---

## 一、准备

| 项 | 说明 | 成本 |
| --- | --- | --- |
| 腾讯云账号 | 实名认证 | 免费 |
| 域名 | `.cn`（约 ¥29/年）或 `.com`（约 ¥55/年）；**中国大陆节点需 ICP 备案**（免费，约 2-20 个工作日） | ¥29-55/年 |
| SSL 证书 | 腾讯云免费 DV 证书（1 年） | 免费 |

> 若不想备案：EdgeOne 选**境外/港澳台节点** + 域名解析到境外，可免备案，但国内访问延迟略高。

---

## 二、CVM 选购与初始化

**配置建议**（后端含本地 fastembed 推理，吃 CPU/内存）：

| 档位 | 规格 | 适用 | 参考价 |
| --- | --- | --- | --- |
| 经济档 | 轻量应用服务器 2核4G 5M + 60GB SSD | 个人/演示（并发小） | ≈ ¥188/年 |
| 推荐档 | 标准型 S5 4核8G + 100GB SSD | 小团队生产 | ≈ ¥575-1733/年 |

> worker 加载 BGE 模型约占用 1-2GB 内存，Postgres/MinIO 各占几百 MB，**4核8G 更稳**；2核4G 可跑但 embedding 较慢。

**初始化**（Ubuntu 22.04 为例）：
```bash
# Docker + compose 插件
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER && newgrp docker
# 安全组：仅放行 22(SSH)、80、443；不要对公网开放 8000/9000/5432
```

---

## 三、后端部署（docker-compose）

```bash
git clone <repo> && cd web-agent
cp .env.example .env   # 编辑：DEEPSEEK_API_KEY、MODEL_CONFIG_ENCRYPTION_KEY、CORS_ORIGINS、DEPLOY_PROFILE=production
docker compose up -d --build
```

- `.env` 关键项：
  - `DEPLOY_PROFILE=production`（Postgres + MinIO + fastembed + 禁 hash）
  - `DEEPSEEK_API_KEY=sk-...`（真实密钥，**只放服务端**）
  - `MODEL_CONFIG_ENCRYPTION_KEY=<Fernet key>`
  - `CORS_ORIGINS=https://你的域名`（直连子域名方式才需要；同源反代可留默认）
- 验证：`curl http://127.0.0.1:8000/api/healthz` 返回 `{"status":"ok"}`；`docker compose ps` 全 `healthy`。
- 数据库/存储：默认走 compose 内的 Postgres+pgvector 与 MinIO（**零额外费用**）。

---

## 四、前端部署到 EdgeOne Pages

1. EdgeOne 控制台 → **Pages** → 创建项目 → 连接 Git（或上传 `frontend/dist`）。
2. 构建：框架 **Vite**、根目录 `frontend`、命令 `npm run build`、输出 `dist`、Node 20。
3. 环境变量：`VITE_API_BASE_URL` **留空**（走同源反代）。
4. 部署后得 `xxx.edgeone.app`，绑定自定义域名 `qa.example.com` 并配 HTTPS。

## 五、EdgeOne 反代 `/api` 回源 CVM

1. 站点 → **规则引擎**：`/api/*` → 回源 `<CVM_IP>:8000`（或 nginx 443）；其余路径 → Pages 静态资源。
2. **SSE 必须**：`/api/*` **关闭缓存**、开启**分块透传**、**回源读超时 ≥ 120s**。
3. 实测一次流式回答，确认逐 token 到达（整段返回 = 缓存/缓冲没关）。

---

## 六、预算（人民币，以控制台实时价为准）

### 档位 1：经济档（个人/演示，全容器 CVM + EdgeOne 个人版）

| 项目 | 配置 | 月成本 | 年成本 |
| --- | --- | --- | --- |
| CVM | 轻量 2核4G 5M | ≈ ¥16 | ≈ ¥188 |
| EdgeOne | 个人版（50GB 流量 + 300 万请求/月） | ¥0 | ¥0 |
| 域名 | .cn | ≈ ¥3 | ≈ ¥29 |
| SSL | 免费 DV | ¥0 | ¥0 |
| **合计** | | **≈ ¥19/月** | **≈ ¥217/年** |

> 注：本地 fastembed 免云端 embedding 费；Postgres/MinIO 走容器免托管费。DeepSeek API 按 token 另计（见末节）。

### 档位 2：推荐档（小团队生产，标准 CVM + EdgeOne 基础）

| 项目 | 配置 | 月成本 | 年成本 |
| --- | --- | --- | --- |
| CVM | 标准型 4核8G | ≈ ¥80 | ≈ ¥1000 |
| 数据盘 | 100GB SSD 云硬盘 | ≈ ¥40 | ≈ ¥480 |
| EdgeOne | 基础版（流量超出个人版时） | ≈ ¥0-100 | ≈ ¥0-1200 |
| 域名 | .com | ≈ ¥5 | ≈ ¥55 |
| SSL | 免费 DV | ¥0 | ¥0 |
| **合计** | | **≈ ¥125-225/月** | **≈ ¥1500-2700/年** |

### 档位 3：省心托管档（生产，DB/存储托管化）

| 项目 | 配置 | 月成本 | 年成本 |
| --- | --- | --- | --- |
| CVM | 4核8G（仅无状态 backend+worker） | ≈ ¥80 | ≈ ¥1000 |
| TencentDB for PostgreSQL | 含 pgvector，入门 1核2G | ≈ ¥200-400 | ≈ ¥2400-4800 |
| COS 对象存储 | 100GB + 流量/请求 | ≈ ¥20-50 | ≈ ¥240-600 |
| EdgeOne | 基础版 | ≈ ¥100 | ≈ ¥1200 |
| 域名 + 证书 | .com + 免费 DV | ≈ ¥5 | ≈ ¥55 |
| **合计** | | **≈ ¥405-635/月** | **≈ ¥4900-7700/年** |

> 档位 3 用托管 DB/COS 换运维省心与高可用，适合正式生产；演示/小团队用档位 1-2（容器化 DB/存储）即可，省约 60-70%。

### DeepSeek API 费用（与部署无关，按 token 另计）
- 输入 ¥2 / 百万 tokens、输出 ¥8 / 百万 tokens（`.env` 可调）。
- 个人演示每月通常 < ¥10；小团队按实际问答量估算（管理后台可看用量/成本）。

---

## 七、成本优化建议

1. **优先档位 1 起步**：EdgeOne 个人版免费 + 轻量 CVM，几乎零成本跑通全流程，验证后再升档。
2. **本地 embedding 是省钱关键**：fastembed 离线免费，替代云端 embedding API（省去每百万 token 的向量化费）。
3. **DB/存储先用容器**：档位 1-2 用 compose 内 Postgres/MinIO，比托管省 ¥200-450/月；数据量大/要高可用再迁 TencentDB/COS。
4. **带宽计费**：轻量 CVM 套餐含流量包（如 500GB/月），个人演示够用；超出按量。
5. **关注促销**：CVM 新客首单/秒杀价常低至 1-3 折（如 4核8G 首单 ¥575/年）。

---

## 八、上线检查清单

- [ ] `https://域名/api/healthz` 返回 `{"status":"ok"}`
- [ ] 登录成功，发起对话 **SSE 逐 token**（非整段）
- [ ] 上传文档 → worker 切分 → 问答带引用
- [ ] 管理后台用量/成本可见
- [ ] 安全组未对公网开放 8000/9000/5432

> 价格均为公开参考价/区间，随地域、促销、计费模式（包年包月 vs 按量）波动，**下单前以腾讯云控制台「价格计算器」实时报价为准**。
