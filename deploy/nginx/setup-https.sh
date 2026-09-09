#!/usr/bin/env bash
# 一键配置 HTTPS：申请 Let's Encrypt 证书并渲染 nginx 配置。
#
# 前置：
#   1. 域名已解析到本机公网 IP（A 记录）
#   2. 80/443 端口已开放（防火墙/安全组）
#   3. 已安装 docker 与 docker compose
#
# 用法：
#   chmod +x setup-https.sh
#   ./setup-https.sh qa.example.com admin@example.com
set -euo pipefail

SERVER_NAME="${1:?用法: $0 <域名> <邮箱>}"
EMAIL="${2:?用法: $0 <域名> <邮箱>}"
COMPOSE_FILE="$(cd "$(dirname "$0")/../.." && pwd)/docker-compose.yml"
NGINX_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/4] 渲染 nginx 配置（域名: ${SERVER_NAME}）"
export SERVER_NAME
envsubst '${SERVER_NAME}' < "${NGINX_DIR}/nginx.conf" > "${NGINX_DIR}/nginx.rendered.conf"

echo "[2/4] 启动证书申请临时容器（webroot 模式）"
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

echo "[3/4] 证书已签发，挂载到 nginx"
# docker-compose 中 nginx 服务挂载 ./deploy/nginx/certbot/conf:/etc/letsencrypt:ro

echo "[4/4] 启动生产栈（含 nginx）"
docker compose -f "${COMPOSE_FILE}" --profile production up -d --build

echo "完成。访问 https://${SERVER_NAME}"
echo "证书自动续期：见 docs/backup-restore.md 的 certbot renew 定时任务"
