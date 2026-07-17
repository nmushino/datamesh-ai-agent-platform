#!/bin/bash
set -e
# =============================================================================
# Script Name: fix-chat-ui-urls.sh
# Description: chat-ui / ai-agent-orchestrator の外部URL系環境変数
#              (API_BASE_URL, KEYCLOAK_URL, OPENMETADATA_URL, DEVELOPER_HUB_URL,
#              OPENMETADATA_PUBLIC_URL) を、各サービスのRouteホスト名から再設定する。
#
#              背景: deployment/kustomize/base/chat-ui/deployment.yaml の
#              ConfigMap/env定義ではこれらのデフォルトが空文字列になっており、
#              本来は deploy.sh が各Routeのホスト名を検出して都度
#              `oc set env` で上書きする設計になっている。しかし
#              `oc apply -k deployment/kustomize/overlays/<env>` を deploy.sh を
#              介さず直接実行すると、これらの環境変数が空文字列に戻ってしまい、
#              ブラウザ(chat-ui)がKeycloak等への絶対URLではなく相対パスで
#              リクエストしてしまう(結果、chat-ui自身のSPA HTMLが返り
#              "Invalid response Content-Type: text/html" のようなエラーになる)。
#
#              ロジックは scripts/deploy.sh の該当箇所 (chat-ui へのRoute反映部分)
#              と同じものを切り出したもの。deploy.sh を使ったフルデプロイの場合は
#              このスクリプトは不要。
# Author: Noriaki Mushino
# Date Created: 2026-07-17
# Last Modified: 2026-07-17
# Version: 1.0
#
# Usage:
#   ./scripts/fix-chat-ui-urls.sh [NAMESPACE] [KEYCLOAK_NAMESPACE]
#
#   NAMESPACE           - chat-ui/ai-agent-orchestrator がデプロイされている namespace (既定: ai-agent-platform)
#   KEYCLOAK_NAMESPACE  - Keycloak が導入済みの namespace (既定: keycloak)
#
# Prerequisites:
#   - OpenShift CLI (oc) が導入済み・ログイン済みであること
#   - ai-agent-orchestrator / keycloak の Route が作成済みであること
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RESET='\033[0m'

NAMESPACE="${1:-ai-agent-platform}"
KEYCLOAK_NAMESPACE="${2:-keycloak}"

command -v oc &>/dev/null || { echo -e "${RED}エラー: oc (OpenShift CLI) が必要です${RESET}" >&2; exit 1; }
oc whoami &>/dev/null || { echo -e "${RED}エラー: oc login が必要です${RESET}" >&2; exit 1; }

echo -e "${BLUE}Route ホスト名を取得中...${RESET}"
AI_AGENT_ROUTE_HOST="$(oc get route ai-agent-orchestrator -n "$NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null || true)"
KEYCLOAK_ROUTE_HOST="$(oc get route keycloak -n "$KEYCLOAK_NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null || true)"

if [ -z "$AI_AGENT_ROUTE_HOST" ]; then
    echo -e "${RED}エラー: namespace '${NAMESPACE}' に Route 'ai-agent-orchestrator' が見つかりませんでした。${RESET}" >&2
    exit 1
fi
if [ -z "$KEYCLOAK_ROUTE_HOST" ]; then
    echo -e "${RED}エラー: namespace '${KEYCLOAK_NAMESPACE}' に Route 'keycloak' が見つかりませんでした。${RESET}" >&2
    exit 1
fi
echo "  ai-agent-orchestrator: ${AI_AGENT_ROUTE_HOST}"
echo "  keycloak              : ${KEYCLOAK_ROUTE_HOST}"

APPS_DOMAIN="${APPS_DOMAIN:-${AI_AGENT_ROUTE_HOST#*.}}"
OPENMETADATA_PUBLIC_BASE_URL="${OPENMETADATA_PUBLIC_BASE_URL:-http://openmetadata-openmetadata.${APPS_DOMAIN}}"
OPENMETADATA_URL="${OPENMETADATA_URL:-${OPENMETADATA_PUBLIC_BASE_URL}/my-data}"
DEVELOPER_HUB_URL="${DEVELOPER_HUB_URL:-https://backstage-developer-hub-quarkusdroneshop-rhdh.${APPS_DOMAIN}}"

echo -e "${BLUE}chat-ui の環境変数を更新中...${RESET}"
oc set env deployment/chat-ui -n "$NAMESPACE" \
    "API_BASE_URL=https://${AI_AGENT_ROUTE_HOST}" \
    "KEYCLOAK_URL=https://${KEYCLOAK_ROUTE_HOST}" \
    "OPENMETADATA_URL=${OPENMETADATA_URL}" \
    "DEVELOPER_HUB_URL=${DEVELOPER_HUB_URL}" >/dev/null

echo -e "${BLUE}ai-agent-orchestrator の環境変数を更新中...${RESET}"
oc set env deployment/ai-agent-orchestrator -n "$NAMESPACE" \
    "OPENMETADATA_PUBLIC_URL=${OPENMETADATA_PUBLIC_BASE_URL}" >/dev/null

echo -e "${GREEN}完了しました。${RESET}"
echo -e "${YELLOW}'oc set env' はロールアウトを自動的にトリガーします。'oc rollout status deployment/chat-ui -n ${NAMESPACE}' で反映を確認してください。${RESET}"
