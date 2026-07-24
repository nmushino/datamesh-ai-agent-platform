#!/bin/bash
set -e
# =============================================================================
# Script Name: provision-site-mm2-tokens.sh
# Description: A/B/C サイト(quarkusdroneshop-demo が動く各OpenShiftクラスタ)
#              それぞれに、quarkusdroneshop-demo 名前空間限定で
#              KafkaTopic / KafkaMirrorMaker2 (Strimzi) の get/list/create/
#              update/patch のみを許可する最小権限の ServiceAccount + Role を
#              作成し、そのAPIサーバーアドレス/トークンを ai-agent-platform
#              namespace の Secret として保存する。
#
#              tools/kafka/admin_tools.py の _mm2_api_config() が読む
#              <SITE>_MM2_API_SERVER / <SITE>_MM2_TOKEN 環境変数
#              (deployment/kustomize/base/ai-agent/deployment.yaml で
#              <site>-mm2-pause-token Secret から注入) の元になる。
#              この認証情報は create_kafka_topic の managed=True 経路
#              (KafkaTopic CR 作成) と、delete_kafka_topic の MM2一時停止/
#              再開の両方で使われる。
#
#              scripts/provision-site-view-tokens.sh (閲覧専用トークン) と
#              同じパターンだが、こちらは書き込み(patch/create/update)権限を
#              付与する点が異なる。ただし対象リソースは kafkatopics /
#              kafkamirrormaker2s のみに絞り、それ以外への書き込みは一切
#              許可しない(namespace-scoped Role、ClusterRole は使わない)。
#
# Author: Datamesh AI Agent Platform Team
# Date Created: 2026-07-24
#
# Usage:
#   ./scripts/provision-site-mm2-tokens.sh
#
#   実行前に、AI Agent Platform 本体(ai-agent-platform namespace)が
#   動いているクラスタに `oc login` しておくこと。スクリプトは各サイトへ
#   ログインを切り替えながら作業した後、必ず元のクラスタ・contextに戻る。
#
#   各サイトのログイン情報は以下の環境変数で渡す(未設定のサイトはスキップし、
#   対応する Secret は作成しない → 該当サイトは managed=True でのCR作成が
#   K8s API 認証情報未設定エラーになる):
#     ASITE_API_SERVER / ASITE_ADMIN_USER / ASITE_ADMIN_PASSWORD
#     BSITE_API_SERVER / BSITE_ADMIN_USER / BSITE_ADMIN_PASSWORD
#     CSITE_API_SERVER / CSITE_ADMIN_USER / CSITE_ADMIN_PASSWORD
#
#   NAMESPACE          - AI Agent Platform 本体の namespace (既定: ai-agent-platform)
#   SITE_NAMESPACE     - 各サイト側で対象にする namespace (既定: quarkusdroneshop-demo)
#
# Prerequisites:
#   - OpenShift CLI (oc) が導入済みであること
#   - AI Agent Platform 本体クラスタに oc login 済みであること
#   - 各サイトクラスタに対する管理者相当の認証情報 (Role/SA作成に必要)
# =============================================================================

NAMESPACE="${NAMESPACE:-ai-agent-platform}"
SITE_NAMESPACE="${SITE_NAMESPACE:-quarkusdroneshop-demo}"
SA="ai-agent-mm2-operator"
ROLE="ai-agent-mm2-operator"

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

  echo -e "${BLUE}[${site}] ServiceAccount (${SA}) と最小権限 Role を作成中...${RESET}"
  oc create serviceaccount "$SA" -n "$SITE_NAMESPACE" --dry-run=client -o yaml | oc apply -f - >/dev/null

  cat <<EOF | oc apply -f - >/dev/null
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ${ROLE}
  namespace: ${SITE_NAMESPACE}
rules:
  - apiGroups: ["kafka.strimzi.io"]
    resources: ["kafkatopics", "kafkamirrormaker2s"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
EOF

  cat <<EOF | oc apply -f - >/dev/null
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ${ROLE}
  namespace: ${SITE_NAMESPACE}
subjects:
  - kind: ServiceAccount
    name: ${SA}
    namespace: ${SITE_NAMESPACE}
roleRef:
  kind: Role
  name: ${ROLE}
  apiGroup: rbac.authorization.k8s.io
EOF

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

  echo "$server" > "/tmp/${site}_mm2_api_server.txt"
  echo "$token" > "/tmp/${site}_mm2_token.txt"
  echo -e "${GREEN}[${site}] 完了 (トークン長: ${#token})${RESET}"
}

for site in "${SITES[@]}"; do
  provision_site "$site"
done

echo -e "${BLUE}AI Agent Platform 本体クラスタへ戻ります (context: ${ORIGINAL_CONTEXT})${RESET}"
oc config use-context "$ORIGINAL_CONTEXT" >/dev/null

echo -e "${BLUE}${NAMESPACE} namespace に Secret を作成中...${RESET}"
for site in "${SITES[@]}"; do
  server_file="/tmp/${site}_mm2_api_server.txt"
  token_file="/tmp/${site}_mm2_token.txt"
  if [ ! -f "$server_file" ] || [ ! -f "$token_file" ]; then
    continue
  fi
  oc create secret generic "${site}-mm2-pause-token" \
    -n "$NAMESPACE" \
    --from-file=api-server="$server_file" \
    --from-file=token="$token_file" \
    --dry-run=client -o yaml | oc apply -f - >/dev/null
  echo -e "${GREEN}  → ${site}-mm2-pause-token を作成しました${RESET}"
  rm -f "$server_file" "$token_file"
done

echo -e "${GREEN}完了しました。deployment/kustomize/base/ai-agent/deployment.yaml の環境変数定義に従い、"
echo -e "次回 ai-agent-orchestrator のロールアウト(oc rollout restart)で反映されます。${RESET}"
