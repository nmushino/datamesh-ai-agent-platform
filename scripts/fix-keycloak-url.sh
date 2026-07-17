#!/bin/bash
set -e
# =============================================================================
# Script Name: fix-keycloak-url.sh
# Description: business-api-config ConfigMap の keycloak-url を、Keycloak の
#              外部Route URLに再設定する。
#
#              背景: deployment/kustomize/base/business-api/deployment.yaml の
#              ConfigMap定義では keycloak-url のデフォルトが空文字列になっており、
#              本来は deploy.sh が Keycloak の Route ホスト名を検出して都度
#              上書きパッチする設計になっている。しかし
#              `oc apply -k deployment/kustomize/overlays/<env>` を deploy.sh を
#              介さず直接実行すると、この ConfigMap がベース定義の空文字列で
#              上書きされてしまい、business-api が
#              'quarkus.oidc.auth-server-url' を解決できず起動に失敗する
#              (URI is not absolute / OIDCException)。
#
#              business-api はトークンの iss claim を外部Route URLと一致させる
#              必要があるため、内部Service URL (keycloak.keycloak.svc.cluster.local)
#              ではなく必ず外部Route URLを使うこと。
#
#              `oc apply -k` を実行するたびに(deploy.sh を使わない場合は)本
#              スクリプトを再実行すること。
# Author: Noriaki Mushino
# Date Created: 2026-07-17
# Last Modified: 2026-07-17
# Version: 1.0
#
# Usage:
#   ./scripts/fix-keycloak-url.sh [NAMESPACE] [KEYCLOAK_NAMESPACE]
#
#   NAMESPACE          - business-api がデプロイされている namespace (既定: ai-agent-platform)
#   KEYCLOAK_NAMESPACE - Keycloak が導入済みの namespace (既定: keycloak)
#
# Prerequisites:
#   - OpenShift CLI (oc) が導入済み・ログイン済みであること
#   - Keycloak の Route (名前: keycloak) が KEYCLOAK_NAMESPACE に存在すること
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RESET='\033[0m'

NAMESPACE="${1:-ai-agent-platform}"
KEYCLOAK_NAMESPACE="${2:-keycloak}"

command -v oc &>/dev/null || { echo -e "${RED}エラー: oc (OpenShift CLI) が必要です${RESET}" >&2; exit 1; }
oc whoami &>/dev/null || { echo -e "${RED}エラー: oc login が必要です${RESET}" >&2; exit 1; }

echo -e "${BLUE}Keycloak の外部Route ホスト名を取得中 (namespace=${KEYCLOAK_NAMESPACE})...${RESET}"
KEYCLOAK_ROUTE_HOST="$(oc get route keycloak -n "$KEYCLOAK_NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null || true)"

if [ -z "$KEYCLOAK_ROUTE_HOST" ]; then
    echo -e "${RED}エラー: namespace '${KEYCLOAK_NAMESPACE}' に Route 'keycloak' が見つかりませんでした。${RESET}" >&2
    echo -e "${RED}  'oc get route -n ${KEYCLOAK_NAMESPACE}' で実際の Route 名を確認してください。${RESET}" >&2
    exit 1
fi
echo "  Route host: ${KEYCLOAK_ROUTE_HOST}"

if ! oc get configmap business-api-config -n "$NAMESPACE" &>/dev/null; then
    echo -e "${RED}エラー: ConfigMap 'business-api-config' が namespace '${NAMESPACE}' に見つかりません。${RESET}" >&2
    exit 1
fi

CURRENT_URL="$(oc get configmap business-api-config -n "$NAMESPACE" -o jsonpath='{.data.keycloak-url}' 2>/dev/null || true)"
NEW_URL="https://${KEYCLOAK_ROUTE_HOST}"

if [ "$CURRENT_URL" = "$NEW_URL" ]; then
    echo -e "${GREEN}既に正しい値が設定されています (${NEW_URL})。パッチ不要です。${RESET}"
else
    echo -e "${BLUE}ConfigMap を更新中... (${CURRENT_URL:-<空>} -> ${NEW_URL})${RESET}"
    oc patch configmap business-api-config -n "$NAMESPACE" --type merge \
        -p "{\"data\":{\"keycloak-url\":\"${NEW_URL}\"}}" >/dev/null
    echo -e "${GREEN}ConfigMap を更新しました。${RESET}"

    echo -e "${BLUE}business-api を再起動中...${RESET}"
    oc rollout restart deployment/business-api -n "$NAMESPACE" >/dev/null
    oc rollout status deployment/business-api -n "$NAMESPACE"
fi
