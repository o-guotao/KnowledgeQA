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
#   ./setup-https.sh example.com admin@example.com "www.example.com"   # 主域名 + www（ICP 合规要求双域名可访问）
set -euo pipefail

SERVER_NAME="${1:?用法: $0 <域名> <邮箱> [附加域名...]}"
EMAIL="${2:?用法: $0 <域名> <邮箱> [附加域名...]}"
shift 2
EXTRA_DOMAINS="${*:-}"   # 附加域名（空格分隔，如 "www.example.com"），无则留空
COMPOSE_FILE="$(cd "$(dirname "$0")/../.." && pwd)/docker-compose.yml"
NGINX_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/4] 渲染 nginx 配置（域名: ${SERVER_NAME} ${EXTRA_DOMAINS}）"
export SERVER_NAME EXTRA_DOMAINS
envsubst '${SERVER_NAME} ${EXTRA_DOMAINS}' < "${NGINX_DIR}/nginx.conf" > "${NGINX_DIR}/nginx.rendered.conf"

echo "[2/4] 启动证书申请临时容器（webroot 模式）"
mkdir -p "${NGINX_DIR}/certbot/www" "${NGINX_DIR}/certbot/conf"

# 证书域名列表：主域名 + 附加域名（每个 -d 一个，证书覆盖双域名）
CERTBOT_DOMAINS=(-d "${SERVER_NAME}")
for d in ${EXTRA_DOMAINS}; do
  CERTBOT_DOMAINS+=(-d "${d}")
done

docker run --rm \
  -v "${NGINX_DIR}/certbot/conf:/etc/letsencrypt" \
  -v "${NGINX_DIR}/certbot/www:/var/www/certbot" \
  -p 80:80 \
  certbot/certbot certonly --standalone \
  --preferred-challenges http \
  --email "${EMAIL}" \
  --agree-tos --no-eff-email \
  "${CERTBOT_DOMAINS[@]}"

echo "[3/4] 证书已签发，挂载到 nginx"
# docker-compose 中 nginx 服务挂载 ./deploy/nginx/certbot/conf:/etc/letsencrypt:ro

echo "[4/4] 启动生产栈（含 nginx）"
docker compose -f "${COMPOSE_FILE}" --profile production up -d --build

echo "完成。访问 https://${SERVER_NAME}"
echo "证书自动续期：见 docs/backup-restore.md 的 certbot renew 定时任务"
