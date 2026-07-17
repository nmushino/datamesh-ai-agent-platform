#!/bin/bash
set -e
# =============================================================================
# Script Name: apply-kustomize.sh
# Description: deploy.sh を使わずに Kustomize マニフェストだけを再適用したい時の
#              ラッパー。`oc apply -k` は business-api-config ConfigMap の
#              keycloak-url や chat-ui/ai-agent-orchestrator の外部URL系環境変数を
#              ベース定義の空文字列で上書きしてしまうため、適用後に必ず
#              scripts/fix-keycloak-url.sh と scripts/fix-chat-ui-urls.sh を実行して
#              各RouteのURLへ復元する。この手順を毎回手動で覚えておく必要が
#              ないようにするためのスクリプト。
#
#              (deploy.sh を使ったフルデプロイの場合は、deploy.sh 内で同様の
#              順序が組み込まれているためこのスクリプトは不要)
# Author: Noriaki Mushino
# Date Created: 2026-07-17
# Last Modified: 2026-07-17
# Version: 1.0
#
# Usage:
#   ./scripts/apply-kustomize.sh [ENV] [NAMESPACE] [KEYCLOAK_NAMESPACE]
#
#   ENV                 - dev(既定) / staging / prod
#   NAMESPACE           - business-api がデプロイされている namespace (既定: ai-agent-platform)
#   KEYCLOAK_NAMESPACE  - Keycloak が導入済みの namespace (既定: keycloak)
#
# Prerequisites:
#   - OpenShift CLI (oc) が導入済み・ログイン済みであること
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RESET='\033[0m'

ENV="${1:-dev}"
NAMESPACE="${2:-ai-agent-platform}"
KEYCLOAK_NAMESPACE="${3:-keycloak}"

command -v oc &>/dev/null || { echo -e "${RED}エラー: oc (OpenShift CLI) が必要です${RESET}" >&2; exit 1; }
oc whoami &>/dev/null || { echo -e "${RED}エラー: oc login が必要です${RESET}" >&2; exit 1; }

OVERLAY_DIR="${REPO_ROOT}/deployment/kustomize/overlays/${ENV}"
if [ ! -d "$OVERLAY_DIR" ]; then
    echo -e "${RED}エラー: ${OVERLAY_DIR} が見つかりません。ENV は dev/staging/prod のいずれかです。${RESET}" >&2
    exit 1
fi

echo -e "${BLUE}[1/3] Kustomize (${ENV}) を適用中...${RESET}"
oc apply -k "$OVERLAY_DIR"

echo -e "${BLUE}[2/3] business-api の keycloak-url を Keycloak 外部Route URLへ復元中...${RESET}"
"${SCRIPT_DIR}/fix-keycloak-url.sh" "$NAMESPACE" "$KEYCLOAK_NAMESPACE"

echo -e "${BLUE}[3/3] chat-ui / ai-agent-orchestrator の外部URL系環境変数を復元中...${RESET}"
"${SCRIPT_DIR}/fix-chat-ui-urls.sh" "$NAMESPACE" "$KEYCLOAK_NAMESPACE"

echo -e "${GREEN}完了しました。${RESET}"
