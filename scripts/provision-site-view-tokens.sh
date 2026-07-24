#!/bin/bash
set -e
# =============================================================================
# Script Name: provision-site-view-tokens.sh
# Description: A/B/C サイト(quarkusdroneshop-demo が動く各OpenShiftクラスタ)
#              それぞれに、閲覧専用 (view ロール) の ServiceAccount と
#              long-lived トークンを作成し、そのAPIサーバーアドレス/トークンを
#              ai-agent-platform namespace の Secret として保存する。
#
#              tools/openshift/openshift_tools.py の list_namespaces /
#              get_pods / list_services / list_routes (site引数付き) が使う
#              <SITE>_K8S_API_SERVER / <SITE>_K8S_TOKEN 環境変数の元になる。
#              (tools/kafka/admin_tools.py の MM2一時停止用トークン
#              <site>-mm2-pause-token と同じ構成パターン。ただしこちらは
#              view ロールで読み取り専用、書き込み権限は一切付与しない)
#
# Author: Datamesh AI Agent Platform Team
# Date Created: 2026-07-17
#
# Usage:
#   ./scripts/provision-site-view-tokens.sh
#
#   実行前に、AI Agent Platform 本体(ai-agent-platform namespace)が
#   動いているクラスタに `oc login` しておくこと。スクリプトは各サイトへ
#   ログインを切り替えながら作業した後、必ず元のクラスタ・contextに戻る。
#
#   各サイトのログイン情報は以下の環境変数で渡す(未設定のサイトはスキップし、
#   対応する Secret は作成しない → 該当サイトは自身のドメイン扱いにならず、
#   ツール呼び出し時にエラーメッセージで通知される):
#     ASITE_API_SERVER / ASITE_ADMIN_USER / ASITE_ADMIN_PASSWORD
#     BSITE_API_SERVER / BSITE_ADMIN_USER / BSITE_ADMIN_PASSWORD
#     CSITE_API_SERVER / CSITE_ADMIN_USER / CSITE_ADMIN_PASSWORD
#
#   NAMESPACE          - AI Agent Platform 本体の namespace (既定: ai-agent-platform)
#   SITE_NAMESPACE     - 各サイト側で閲覧対象にする namespace (既定: quarkusdroneshop-demo)
#
# Prerequisites:
#   - OpenShift CLI (oc) が導入済みであること
#   - AI Agent Platform 本体クラスタに oc login 済みであること
#   - 各サイトクラスタに対する管理者相当の認証情報 (SA作成・ClusterRoleBinding付与に必要)
# =============================================================================

NAMESPACE="${NAMESPACE:-ai-agent-platform}"
SITE_NAMESPACE="${SITE_NAMESPACE:-quarkusdroneshop-demo}"
SA="ai-agent-k8s-viewer"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RESET='\033[0m'

command -v oc &>/dev/null || { echo -e "${RED}エラー: oc (OpenShift CLI) が必要です${RESET}" >&2; exit 1; }
oc whoami &>/dev/null || { echo -e "${RED}エラー: 先に AI Agent Platform 本体クラスタへ oc login してください${RESET}" >&2; exit 1; }

ORIGINAL_CONTEXT="$(oc config current-context)"
echo -e "${BLUE}AI Agent Platform 本体クラスタ: $(oc whoami --show-server) (context: ${ORIGINAL_CONTEXT})${RESET}"

# サイト名:APIサーバー環境変数プレフィックス の組
SITES=("asite" "bsite" "csite")

provision_site() {
  local site="$1"
  local prefix
  prefix="$(echo "$site" | tr '[:lower:]' '[:upper:]')"
  local server_var="${prefix}_API_SERVER"
  local user_var="${prefix}_ADMIN_USER"
  local pass_var="${prefix}_ADMIN_PASSWORD"
  local server="${!server_var:-}"
  local user="${!user_var:-}"
  local pass="${!pass_var:-}"

  if [ -z "$server" ] || [ -z "$user" ] || [ -z "$pass" ]; then
    echo -e "${YELLOW}[${site}] スキップ: ${server_var}/${user_var}/${pass_var} が未設定です${RESET}"
    return 0
  fi

  echo -e "${BLUE}[${site}] ${server} にログイン中...${RESET}"
  oc login "$server" -u "$user" -p "$pass" --insecure-skip-tls-verify=true >/dev/null
  oc project "$SITE_NAMESPACE" >/dev/null

  echo -e "${BLUE}[${site}] ServiceAccount (${SA}) を作成し view 権限を付与中...${RESET}"
  oc create serviceaccount "$SA" -n "$SITE_NAMESPACE" --dry-run=client -o yaml | oc apply -f - >/dev/null
  oc adm policy add-cluster-role-to-user view -z "$SA" -n "$SITE_NAMESPACE" >/dev/null

  cat <<EOF | oc apply -f - >/dev/null
apiVersion: v1
kind: Secret
metadata:
  name: ${SA}-longlived-token
  namespace: ${SITE_NAMESPACE}
  annotations:
    kubernetes.io/service-account.name: ${SA}
type: kubernetes.io/service-account-token
EOF
  # トークンが Secret に反映されるまで少し待つ
  sleep 3
  local token
  token="$(oc get secret "${SA}-longlived-token" -n "$SITE_NAMESPACE" -o jsonpath='{.data.token}' | base64 -d)"
  if [ -z "$token" ]; then
    echo -e "${RED}[${site}] エラー: トークンの取得に失敗しました${RESET}" >&2
    return 1
  fi

  printf '%s' "$server" > "/tmp/${site}_k8s_api_server.txt"
  printf '%s' "$token" > "/tmp/${site}_k8s_token.txt"
  echo -e "${GREEN}[${site}] 完了 (トークン長: ${#token})${RESET}"
}

for site in "${SITES[@]}"; do
  provision_site "$site"
done

echo -e "${BLUE}AI Agent Platform 本体クラスタへ戻ります (context: ${ORIGINAL_CONTEXT})${RESET}"
oc config use-context "$ORIGINAL_CONTEXT" >/dev/null

echo -e "${BLUE}${NAMESPACE} namespace に Secret を作成中...${RESET}"
for site in "${SITES[@]}"; do
  server_file="/tmp/${site}_k8s_api_server.txt"
  token_file="/tmp/${site}_k8s_token.txt"
  if [ ! -f "$server_file" ] || [ ! -f "$token_file" ]; then
    continue
  fi
  oc create secret generic "${site}-k8s-view-token" \
    -n "$NAMESPACE" \
    --from-file=api-server="$server_file" \
    --from-file=token="$token_file" \
    --dry-run=client -o yaml | oc apply -f - >/dev/null
  echo -e "${GREEN}  → ${site}-k8s-view-token を作成しました${RESET}"
  rm -f "$server_file" "$token_file"
done

echo -e "${GREEN}完了しました。deployment/kustomize/base/ai-agent/deployment.yaml の環境変数定義に従い、"
echo -e "次回 ai-agent-orchestrator のロールアウト(oc rollout restart)で反映されます。${RESET}"
