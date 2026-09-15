#!/usr/bin/env bash
# 方案 A 回源 HTTPS 一键配置：为回源域名（如 api.example.com）申请 Let's Encrypt
# 证书、渲染 nginx.edgeone.conf，并启动后端与 nginx-edgeone 反代。
#
# 前置：
#   1. 回源域名（api.example.com）A 记录已解析到本机公网 IP
#   2. 防火墙已放行 80/443（申请证书需 80，回源用 443）
#   3. 已装 docker 与 docker compose
#
# 用法：
#   chmod +x setup-https-edgeone.sh
#   ./setup-https-edgeone.sh api.example.com admin@example.com
set -euo pipefail

SERVER_NAME="${1:?用法: $0 <回源域名 如 api.example.com> <邮箱>}"
EMAIL="${2:?用法: $0 <回源域名 如 api.example.com> <邮箱>}"
COMPOSE_FILE="$(cd "$(dirname "$0")/../.." && pwd)/docker-compose.yml"
NGINX_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/4] 渲染方案 A nginx 配置（回源域名: ${SERVER_NAME}）"
export SERVER_NAME
envsubst '${SERVER_NAME}' < "${NGINX_DIR}/nginx.edgeone.conf" > "${NGINX_DIR}/nginx.edgeone.rendered.conf"

echo "[2/4] 申请 Let's Encrypt 证书（webroot/standalone 模式）"
mkdir -p "${NGINX_DIR}/certbot/www" "${NGINX_DIR}/certbot/conf"
docker run --rm \
  -v "${NGINX_DIR}/certbot/conf:/etc/letsencrypt" \
  -v "${NGINX_DIR}/certbot/www:/var/www/certbot" \
  -p 80:80 \
  certbot/certbot certonly --standalone \
  --preferred-challenges http \
  --email "${EMAIL}" \
  --agree-tos --no-eff-email \
  -d "${SERVER_NAME}"

echo "[3/4] 启动后端服务（db/minio/backend/worker）"
docker compose -f "${COMPOSE_FILE}" up -d --build db minio minio-init backend worker

echo "[4/4] 启动方案 A 回源反代 nginx-edgeone"
docker compose -f "${COMPOSE_FILE}" --profile edgeone up -d nginx-edgeone

echo "完成。回源地址：https://${SERVER_NAME}"
echo "健康检查：https://${SERVER_NAME}/healthz 应返回 {\"status\":\"ok\"}"
echo "证书续期：certbot renew（见 docs/backup-restore.md 定时任务）"
