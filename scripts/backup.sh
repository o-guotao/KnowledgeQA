#!/usr/bin/env bash
# 数据备份：Postgres（pg_dump）+ 对象存储（MinIO mirror）+ 配置快照。
#
# 备份内容：
#   - Postgres：全部业务表（users/sessions/messages/tasks/quotas/documents/chunks/model_configs）
#   - MinIO：文档原文（对象存储）
#   - .env：配置快照（含密钥，备份目录需加密或限制权限）
#
# 用法：./scripts/backup.sh [备份目录]（默认 ./backups/YYYYMMDD-HHMMSS）
# 定时：见 docs/backup-restore.md 的 cron 配置
set -euo pipefail

BACKUP_ROOT="${1:-./backups/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "${BACKUP_ROOT}"
echo "备份目录: ${BACKUP_ROOT}"

# 从 .env 读连接信息（docker-compose 内的服务名/凭据）
POSTGRES_USER="${POSTGRES_USER:-webagent}"
POSTGRES_DB="${POSTGRES_DB:-webagent}"
MINIO_BUCKET="${MINIO_BUCKET:-web-agent-docs}"

echo "[1/3] 备份 Postgres -> ${BACKUP_ROOT}/postgres.sql.gz"
docker compose exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists \
  | gzip > "${BACKUP_ROOT}/postgres.sql.gz"

echo "[2/3] 备份 MinIO bucket '${MINIO_BUCKET}' -> ${BACKUP_ROOT}/minio/"
docker compose exec -T minio sh -c "tar czf - -C /data ${MINIO_BUCKET}" \
  > "${BACKUP_ROOT}/minio.tar.gz" || echo "  (MinIO 备份失败或为空，跳过)"

echo "[3/3] 快照配置 .env -> ${BACKUP_ROOT}/.env.backup"
cp .env "${BACKUP_ROOT}/.env.backup"
chmod 600 "${BACKUP_ROOT}/.env.backup"

# 清单
cat > "${BACKUP_ROOT}/MANIFEST.txt" <<EOF
备份时间: $(date -Iseconds)
Postgres: postgres.sql.gz ($(du -h "${BACKUP_ROOT}/postgres.sql.gz" | cut -f1))
MinIO: minio.tar.gz ($(du -h "${BACKUP_ROOT}/minio.tar.gz" 2>/dev/null | cut -f1 || echo 'N/A'))
配置: .env.backup
恢复: ./scripts/restore.sh ${BACKUP_ROOT}
EOF

echo "备份完成: ${BACKUP_ROOT}"
echo "提示：将备份目录同步到异地/对象存储，本地备份不能防机器损坏"
