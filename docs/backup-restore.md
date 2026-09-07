# 数据备份与恢复

> 备份是生产底线：误删、磁盘损坏、迁移失败都靠备份兜底。本文档给出策略、定时方案与恢复演练。

## 一、备份内容

| 数据 | 位置 | 备份方式 | 恢复关键点 |
| --- | --- | --- | --- |
| 业务表（users/sessions/messages/tasks/quotas/documents/chunks/model_configs） | Postgres | `pg_dump` 全量 | 建表结构含 `--clean --if-exists` 可重入 |
| 文档原文 | MinIO bucket | `tar` 打包 `/data/<bucket>` | 与 documents.object_key 对应 |
| 配置 | `.env` | 复制 | 含密钥，备份目录 `chmod 600`，异地需加密 |
| 向量索引 | pgvector（在表内） | 随 pg_dump | HNSW 索引随表结构重建 |

向量数据存于 `chunks.embedding` 列，随 pg_dump 一并备份，无需单独处理。

## 二、手动备份/恢复

```bash
# 备份（默认输出 ./backups/YYYYMMDD-HHMMSS）
chmod +x scripts/backup.sh scripts/restore.sh
./scripts/backup.sh

# 恢复到指定备份目录（会覆盖当前数据，有确认提示）
./scripts/restore.sh ./backups/20260907-153000
```

备份脚本需在有 `docker` CLI 的宿主机执行（内部用 `docker compose exec`）。

## 三、定时备份（cron）

宿主机 crontab（每天凌晨 2 点备份，保留 14 天）：

```cron
0 2 * * * cd /opt/web-agent && ./scripts/backup.sh >> /var/log/web-agent-backup.log 2>&1
0 3 * * * find /opt/web-agent/backups -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
```

编辑：`crontab -e`，粘贴上面两行。

## 四、异地/云端备份（防机器损坏）

本地备份无法防机器损坏。建议备份后同步到异地：

```bash
# 方式 A：对象存储（如阿里 OSS / 腾讯 COS / S3）
aws s3 sync /opt/web-agent/backups s3://your-backup-bucket/web-agent/ \
  --storage-class STANDARD_IA

# 方式 B：异地服务器（rsync）
rsync -avz --delete /opt/web-agent/backups/ backup-host:/data/web-agent-backups/
```

`.env.backup` 含密钥，异地同步前建议加密：

```bash
tar czf - backups/ | gpg -c > backups-$(date +%Y%m%d).tar.gz.gpg
```

## 五、恢复演练（必须定期做）

备份只有恢复验证过才可信。每季度演练一次：

```bash
# 1. 在测试环境（或临时目录）起一套干净栈
git clone <repo> /tmp/web-agent-restore-test && cd /tmp/web-agent-restore-test
cp .env.example .env   # 配置同生产（除密钥外）
docker compose up -d db minio minio-init

# 2. 从最近备份恢复
./scripts/restore.sh /opt/web-agent/backups/<最近备份目录>

# 3. 验证
docker compose up -d backend worker
# 登录 -> 文档列表非空 -> 提问能召回 -> 引用可回跳

# 4. 清理
docker compose down -v && rm -rf /tmp/web-agent-restore-test
```

## 六、SQLite 本地模式备份

本地无 Docker 演示（`DB_BACKEND=sqlite`）时，备份就是复制两个东西：

```powershell
# PowerShell
Copy-Item backend/webagent.db backend/backups/webagent-$(Get-Date -Format yyyyMMdd).db
Copy-Item -Recurse backend/.local_storage backend/backups/local_storage-$(Get-Date -Format yyyyMMdd)
```

恢复即复制回原路径。

## 七、证书自动续期（HTTPS）

Let's Encrypt 证书 90 天过期，certbot 定时续期：

```cron
0 3 1 * * docker run --rm -v /opt/web-agent/deploy/nginx/certbot/conf:/etc/letsencrypt -v /opt/web-agent/deploy/nginx/certbot/www:/var/www/certbot certbot/certbot renew --quiet && docker compose --profile production exec nginx nginx -s reload
```

## 八、备份策略速查

| 项 | 值 |
| --- | --- |
| 频率 | 每天 1 次（cron 02:00） |
| 保留 | 本地 14 天，异地 90 天 |
| 内容 | Postgres 全量 + MinIO 全量 + .env 快照 |
| 异地 | 对象存储或异地服务器（加密） |
| 演练 | 每季度 1 次恢复验证 |
| RPO（可接受数据丢失） | 24 小时 |
| RTO（恢复时间目标） | < 1 小时 |
