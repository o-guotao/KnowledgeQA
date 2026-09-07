#!/usr/bin/env bash
# 数据恢复：从 backup.sh 生成的备份目录恢复 Postgres 与 MinIO。
#
# 警告：恢复会覆盖当前数据，操作前请确认。
#
# 用法：./scripts/restore.sh <备份目录>
set -euo pipefail

BACKUP_DIR="${1:?用法: $0 <备份目录>}"

if [[ ! -f "${BACKUP_DIR}/postgres.sql.gz" ]]; then
  echo "错误：${BACKUP_DIR} 下无 postgres.sql.gz"
  exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-webagent}"
POSTGRES_DB="${POSTGRES_DB:-webagent}"
MINIO_BUCKET="${MINIO_BUCKET:-web-agent-docs}"

read -r -p "恢复将覆盖当前数据，确认继续？[y/N] " confirm
[[ "${confirm}" == "y" || "${confirm}" == "Y" ]] || { echo "已取消"; exit 0; }

echo "[1/3] 停止 backend/worker（避免恢复期间写入）"
docker compose stop backend worker || true

echo "[2/3] 恢复 Postgres"
gunzip -c "${BACKUP_DIR}/postgres.sql.gz" \
  | docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

if [[ -f "${BACKUP_DIR}/minio.tar.gz" ]]; then
  echo "[3/3] 恢复 MinIO bucket"
  cat "${BACKUP_DIR}/minio.tar.gz" | docker compose exec -T minio sh -c "tar xzf - -C /data"
else
  echo "[3/3] 无 MinIO 备份，跳过"
fi

echo "重启服务"
docker compose up -d backend worker

echo "恢复完成。请验证：登录 -> 文档列表 -> 提问召回"
