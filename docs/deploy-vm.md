# 虚机部署指南

> 目标：在一台干净的 Linux 虚机上把整套系统跑起来，对外可访问。

## 一、虚机规格

| 项 | 最低 | 建议 |
| --- | --- | --- |
| OS | Ubuntu 22.04 / Debian 12（x86_64） | 同左 |
| CPU | 2 vCPU | 4 vCPU（embedding 切分会吃 CPU） |
| 内存 | 4 GB | 8 GB（BGE 模型常驻 + Postgres） |
| 磁盘 | 20 GB | 40 GB（文档 + 模型缓存 + DB） |
| 端口 | 5173（前端）、8000（API）、9001（MinIO 控制台）对外 | 同左 |

> Windows Server 虚机也可（用 Docker Desktop 或 WSL2+Docker Engine），但 Linux 更省心。

## 二、安装 Docker（一次性）

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 让当前用户免 sudo 用 docker（需重新登录生效）
sudo usermod -aG docker $USER
newgrp docker

# 验证
docker --version && docker compose version
```

## 三、拉取代码

```bash
# 方式 A：git（推荐，便于后续 git pull 更新）
sudo apt-get install -y git
git clone <你的仓库地址> /opt/web-agent
cd /opt/web-agent

# 方式 B：从本机打包上传
# 本机：cd d:\code\web-agent && tar -czf web-agent.tar --exclude=node_modules --exclude=.venv --exclude=dist .
# 上传：scp web-agent.tar user@<虚机IP>:/tmp/
# 虚机：mkdir -p /opt/web-agent && tar -xzf /tmp/web-agent.tar -C /opt/web-agent && cd /opt/web-agent
```

## 四、配置环境变量

```bash
cp .env.example .env
nano .env   # 或 vim
```

**必改项**：
- `DEEPSEEK_API_KEY=sk-你的真实key`（没有 key 这一步，对话会报 MODEL_ERROR）
- `JWT_SECRET=` 改成一串随机字符（如 `openssl rand -hex 32` 生成）
- `MINIO_ROOT_PASSWORD=` 改强密码（MinIO 控制台要登录）

其余项保留默认即可。

## 五、启动

```bash
cd /opt/web-agent
docker compose up -d --build      # 首次构建镜像，约 5-10 分钟（下载 BGE 模型较慢）
docker compose logs -f backend    # 看到 alembic upgrade head + seed 完成 + Uvicorn running 即就绪
```

首次启动 worker 会下载 BGE-small-zh 模型（约 100MB，缓存到 `modelcache` 卷，后续重启不再下载）。

## 六、访问

虚机本机访问：`http://localhost:5173`，账号 `demo / demo1234`。

**从你电脑访问虚机**（三种任选）：

1. **直连端口**（虚机有公网 IP 或同内网）：
   - 防火墙放行：`sudo ufw allow 5173,8000,9001/tcp`
   - 浏览器打开 `http://<虚机IP>:5173`
   - 前端访问后端走 Vite 代理，需改 `frontend/vite.config.ts` 的 `target` 为 `http://<虚机IP>:8000`，**或**改用生产构建（见下方）

2. **生产构建**（推荐，无 Vite 代理依赖）：
   ```bash
   docker compose exec frontend npm run build
   # 构建产物已在容器内 /usr/share/nginx/html，nginx 直接提供
   # 访问 http://<虚机IP>:5173 即是静态站 + /api 反代到 backend
   ```

3. **SSH 端口转发**（虚机不对外开端口时）：
   - 本机执行：`ssh -L 5173:localhost:5173 -L 8000:localhost:8000 user@<虚机IP>`
   - 本机浏览器开 `http://localhost:5173`

## 七、日常运维

```bash
docker compose ps                    # 查看服务状态
docker compose logs -f worker        # 看任务处理（切分/embedding/死信）
docker compose logs -f backend        # 看请求与 traceId
docker compose restart backend       # 改代码后重启
docker compose down                  # 停止全部（数据卷保留）
docker compose down -v               # 停止并清空数据（慎用，会丢文档与向量）
docker compose pull && docker compose up -d --build   # 拉新代码后更新
```

## 八、可选：反向代理 + HTTPS（对外正式使用）

用 nginx 反代 + Let's Encrypt 证书：

```nginx
server {
    listen 443 ssl http2;
    server_name qa.yourdomain.com;
    ssl_certificate     /etc/letsencrypt/live/qa.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/qa.yourdomain.com/privkey.pem;

    # 前端静态
    location / {
        proxy_pass http://127.0.0.1:5173;
    }
    # API + SSE（关闭缓冲）
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

证书申请：`sudo certbot --nginx -d qa.yourdomain.com`。

## 九、常见坑

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| worker 一直 `loading embedding model` 卡住 | 首次下载 BGE 模型慢/网络问题 | 等待；或本机下载后拷到卷 |
| 对话报 `MODEL_ERROR: DeepSeek 返回 401` | `DEEPSEEK_API_KEY` 没填或填错 | 改 `.env` 后 `docker compose up -d backend worker` |
| 上传文档后状态一直是 `uploaded` | worker 没起来或报错 | `docker compose logs worker` 看原因 |
| 前端登录后白屏 | 后端没起或 CORS | `docker compose ps` 看是否都 `healthy`；查 backend 日志 |
| 切分任务进 `dead` | 文件损坏/编码问题 | 查 `tasks.error` 字段；换标准 UTF-8 文本重试 |
| 虚机重启后服务没了 | 没设开机自启 | `sudo systemctl enable docker` 已默认；`docker compose up -d` 需手动或加 systemd unit |
