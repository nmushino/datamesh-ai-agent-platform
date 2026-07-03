#!/bin/sh
# 実行時に環境変数から config.js を生成する
# /usr/share/nginx/html は読み取り専用ツリーのため /tmp (常に書き込み可能) に書き出し、
# nginx側 (default.conf) で /config.js をそこから配信するようにしている
set -eu

mkdir -p /tmp/runtime-config
cat > /tmp/runtime-config/config.js <<EOF
window.__APP_CONFIG__ = {
  apiBaseUrl: "${API_BASE_URL:-}",
  keycloakUrl: "${KEYCLOAK_URL:-}",
  keycloakRealm: "${KEYCLOAK_REALM:-drone-platform}",
  keycloakClientId: "${KEYCLOAK_CLIENT_ID:-chat-ui}",
  openMetadataUrl: "${OPENMETADATA_URL:-}",
  developerHubUrl: "${DEVELOPER_HUB_URL:-}"
};
EOF
