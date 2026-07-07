#!/bin/bash
set -e
# =============================================================================
# Script Name: deploy.sh
# Description: Datamesh AI Agent Platform を OpenShift にビルド〜デプロイする
#              (Operatorインストール〜イメージビルド〜Kustomizeデプロイまで一括実行)
# Author: Datamesh AI Agent Platform Team
# Date Created: 2026-06-26
# Last Modified: 2026-07-04
# Version: 1.0
#
# Usage:
#   ./scripts/deploy.sh [ENV] [--init-secrets]
#
#   ENV              - dev(既定) / staging / prod
#   --init-secrets   - 初回のみ指定。postgresql/keycloak/agent-db/openmetadata
#                      各Secretを環境変数から作成する
#
#   Keycloak関連の環境変数 (既存インスタンスを共用するための設定):
#     KEYCLOAK_NAMESPACE          - Keycloakが導入済みのnamespace (既定: keycloak)
#     KEYCLOAK_REALM               - AI Agent用に作成するレルム名 (既定: ai-agent)
#     KEYCLOAK_ADMIN_USER/PASSWORD - Keycloak管理者認証情報
#                                     (未指定時は ${KEYCLOAK_NAMESPACE} namespace の
#                                      keycloak-initial-admin Secretから自動取得)
#     KEYCLOAK_INITIAL_USERNAME/USER_EMAIL/USER_PASSWORD
#                                   - 初期ユーザー(Noriaki Mushino)の作成情報
#                                     (既定: nmushino / nmushino@redhat.com / changeme123)
#
#   例:
#     ./scripts/deploy.sh dev --init-secrets
#     ./scripts/deploy.sh staging
#
# Prerequisites:
#   - OpenShift CLI (oc) が導入済み・ログイン済みであること
#   - Maven (mvn) が導入済みであること (business-apiのビルドに使用)
#   - JDK 21 が導入されていること (macOSでは自動検出、他OSは JAVA_HOME を設定)
#   - oc でクラスタ管理者相当の権限 (Operator/Subscription作成) を持つこと
#   - Keycloakは自前で導入せず、OCPに既に導入済みの共有インスタンス
#     (keycloak namespace) にAI Agent用レルムを作成して利用する
#
# =============================================================================
ENV=${1:-dev}
echo "=== Datamesh AI Agent Platform - Deploy to OpenShift ($ENV) ==="

# 前提確認
command -v oc &>/dev/null || { echo "oc (OpenShift CLI) が必要です"; exit 1; }
command -v mvn &>/dev/null || { echo "maven が必要です"; exit 1; }
oc whoami &>/dev/null || { echo "oc login が必要です"; exit 1; }

NAMESPACE="ai-agent-platform"
# Kafka(AMQ Streams)は環境間で共有し quarkusdroneshop-demo namespace に配置する
# (OpenMetadata も openmetadata namespace の既存インスタンスを共用するため、このplatformでは持たない)
KAFKA_NAMESPACE="quarkusdroneshop-demo"
# Keycloak もこのplatform専用には持たず、OCPに既に導入済みのインスタンス(keycloak namespace)を利用する
KEYCLOAK_NAMESPACE="${KEYCLOAK_NAMESPACE:-keycloak}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-ai-agent}"

# Quarkus 3.12 のビルドは ByteBuddy の都合で JDK 22+ では失敗するため JDK 21 を優先使用する
if [ -z "$JAVA_HOME" ] && command -v /usr/libexec/java_home &>/dev/null && /usr/libexec/java_home -v 21 &>/dev/null; then
  export JAVA_HOME
  JAVA_HOME="$(/usr/libexec/java_home -v 21)"
fi

# Namespace 作成
oc get namespace "$NAMESPACE" &>/dev/null || oc new-project "$NAMESPACE"
oc label namespace "$NAMESPACE" argocd.argoproj.io/managed-by=openshift-gitops --overwrite

# ===== Operator インストール (未導入の場合のみ) =====
# CSV名はパッケージ名と一致しない場合がある(例: amq-streams -> amqstreams.vX.Y.Z)ため
# Subscription の status.installedCSV から実際のCSV名を取得して判定する
# mode: "single" (targetNamespaces指定) または "all" (AllNamespaces、targetNamespacesなし)
install_operator() {
  local name=$1 channel=$2 ns=$3 mode=${4:-single}
  local installed_csv
  installed_csv="$(oc get subscription "$name" -n "$ns" -o jsonpath='{.status.installedCSV}' 2>/dev/null)"
  if [ -n "$installed_csv" ] && oc get csv "$installed_csv" -n "$ns" -o jsonpath='{.status.phase}' 2>/dev/null | grep -q Succeeded; then
    echo "  ${name} (${ns}): 導入済み"
    return
  fi
  echo "  ${name} を ${ns} にインストール中..."
  oc get namespace "$ns" &>/dev/null || oc new-project "$ns" >/dev/null
  local target_ns_yaml=""
  if [ "$mode" == "single" ]; then
    target_ns_yaml="  targetNamespaces:
    - ${ns}"
  fi
  cat <<EOF | oc apply -f - >/dev/null
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: ${ns}-og
  namespace: ${ns}
spec:
${target_ns_yaml}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: ${name}
  namespace: ${ns}
spec:
  channel: ${channel}
  name: ${name}
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
EOF
  for i in $(seq 1 60); do
    installed_csv="$(oc get subscription "$name" -n "$ns" -o jsonpath='{.status.installedCSV}' 2>/dev/null)"
    if [ -n "$installed_csv" ] && oc get csv "$installed_csv" -n "$ns" -o jsonpath='{.status.phase}' 2>/dev/null | grep -q Succeeded; then
      echo "  ${name}: Succeeded (${installed_csv})"
      return
    fi
    sleep 5
  done
  echo "  警告: ${name} のインストール完了を確認できませんでした(タイムアウト、後続処理は続行します)"
}

echo "Operator を確認・インストール中..."
# RHBK(Keycloak) Operatorは keycloak namespace に導入済みの共有インスタンスを使うため、
# このplatformでは導入しない
install_operator amq-streams stable "$KAFKA_NAMESPACE"
# OpenShift AI (RHOAI) — Qwen3-8B を vLLM CPU (KServe) で提供するために必要
install_operator rhods-operator stable-3.x redhat-ods-operator all

# ===== OpenShift AI: DataScienceCluster (kserveのみ有効化、単一ノード想定で他は無効化) =====
if ! oc get datasciencecluster default-dsc &>/dev/null; then
  echo "DataScienceCluster を作成中..."
  cat <<'EOF' | oc apply -f - >/dev/null
apiVersion: datasciencecluster.opendatahub.io/v2
kind: DataScienceCluster
metadata:
  name: default-dsc
spec:
  components:
    kserve:
      managementState: Managed
      rawDeploymentServiceConfig: Headed
    dashboard: {managementState: Removed}
    workbenches: {managementState: Removed}
    modelregistry: {managementState: Removed}
    ray: {managementState: Removed}
    trainingoperator: {managementState: Removed}
    trainer: {managementState: Removed}
    trustyai: {managementState: Removed}
    kueue: {managementState: Removed}
    feastoperator: {managementState: Removed}
    aipipelines: {managementState: Removed}
    mlflowoperator: {managementState: Removed}
    sparkoperator: {managementState: Removed}
    llamastackoperator: {managementState: Removed}
EOF
  for i in $(seq 1 30); do
    phase="$(oc get datasciencecluster default-dsc -o jsonpath='{.status.phase}' 2>/dev/null)"
    [ "$phase" == "Ready" ] && { echo "  DataScienceCluster: Ready"; break; }
    sleep 10
  done
else
  echo "  DataScienceCluster: 導入済み"
fi

# ===== Secret 作成 (初回のみ) =====
if [ "$2" == "--init-secrets" ]; then
  echo "Secret を作成中..."
  PG_PASSWORD="${POSTGRESQL_PASSWORD:-devpass}"

  # openmetadata namespace の既存インスタンスの ingestion-bot トークンを指定する
  # (OpenMetadata UI > Settings > Bots > ingestion-bot > Token)
  oc create secret generic openmetadata-secret \
    --from-literal=jwt-token="${OPENMETADATA_JWT_TOKEN:-placeholder-until-om-bootstrap}" \
    -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

  oc create secret generic postgresql-secret \
    --from-literal=username=postgres \
    --from-literal=password="${PG_PASSWORD}" \
    -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

  oc create secret generic agent-db-secret \
    --from-literal=url="${AGENT_DB_URL:-postgresql://postgres:${PG_PASSWORD}@postgresql:5432/agentdb}" \
    -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

  oc create secret generic keycloak-secret \
    --from-literal=client-secret="${KEYCLOAK_CLIENT_SECRET:-dev-client-secret}" \
    -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -
fi

# ===== Keycloak (keycloak namespace の既存インスタンス) にAI Agent用の =====
# ===== レルム・クライアント・初期ユーザーを作成する =====
# KeycloakRealmImport CRは初回インポートしか反映されず、かつ他namespaceの
# Keycloak CRを跨いで参照できないため、Admin REST APIを直接叩いて冪等に作成する
provision_keycloak() {
  echo "Keycloak (${KEYCLOAK_NAMESPACE} namespace) にレルムを作成中..."

  KEYCLOAK_ROUTE_HOST="$(oc get route keycloak -n "$KEYCLOAK_NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null)"
  if [ -z "$KEYCLOAK_ROUTE_HOST" ]; then
    KEYCLOAK_ROUTE_HOST="$(oc get route -n "$KEYCLOAK_NAMESPACE" -o jsonpath='{.items[0].spec.host}' 2>/dev/null)"
  fi
  if [ -z "$KEYCLOAK_ROUTE_HOST" ]; then
    echo "  警告: ${KEYCLOAK_NAMESPACE} namespace にKeycloakのRouteが見つかりません。レルム作成をスキップします"
    return
  fi

  local admin_user admin_password admin_token base_url auth_header
  admin_user="${KEYCLOAK_ADMIN_USER:-$(oc get secret keycloak-initial-admin -n "$KEYCLOAK_NAMESPACE" -o jsonpath='{.data.username}' 2>/dev/null | base64 -d)}"
  admin_password="${KEYCLOAK_ADMIN_PASSWORD:-$(oc get secret keycloak-initial-admin -n "$KEYCLOAK_NAMESPACE" -o jsonpath='{.data.password}' 2>/dev/null | base64 -d)}"
  if [ -z "$admin_user" ] || [ -z "$admin_password" ]; then
    echo "  警告: Keycloak管理者認証情報を取得できません"
    echo "        (環境変数 KEYCLOAK_ADMIN_USER/KEYCLOAK_ADMIN_PASSWORD で指定するか、"
    echo "         ${KEYCLOAK_NAMESPACE} namespace に keycloak-initial-admin Secret が必要です)"
    echo "        レルム作成をスキップします"
    return
  fi

  admin_token="$(curl -sk -X POST "https://${KEYCLOAK_ROUTE_HOST}/realms/master/protocol/openid-connect/token" \
    -d "grant_type=password" -d "client_id=admin-cli" \
    -d "username=${admin_user}" -d "password=${admin_password}" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)"
  if [ -z "$admin_token" ]; then
    echo "  警告: Keycloak管理者トークンの取得に失敗しました。レルム作成をスキップします"
    return
  fi

  auth_header="Authorization: Bearer ${admin_token}"
  base_url="https://${KEYCLOAK_ROUTE_HOST}/admin/realms"

  if [ "$(curl -sk -o /dev/null -w '%{http_code}' -H "$auth_header" "${base_url}/${KEYCLOAK_REALM}")" != "200" ]; then
    curl -sk -X POST "${base_url}" -H "$auth_header" -H "Content-Type: application/json" \
      -d "{\"id\":\"${KEYCLOAK_REALM}\",\"realm\":\"${KEYCLOAK_REALM}\",\"enabled\":true}" >/dev/null
    echo "  レルム ${KEYCLOAK_REALM} を作成しました"
  else
    echo "  レルム ${KEYCLOAK_REALM}: 作成済み"
  fi

  # business-api用 confidentialクライアント (サービスアカウント有効)
  if [ "$(curl -sk -H "$auth_header" "${base_url}/${KEYCLOAK_REALM}/clients?clientId=business-api" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)" == "0" ]; then
    curl -sk -X POST "${base_url}/${KEYCLOAK_REALM}/clients" -H "$auth_header" -H "Content-Type: application/json" -d "{
      \"clientId\": \"business-api\",
      \"secret\": \"${KEYCLOAK_CLIENT_SECRET:-dev-client-secret}\",
      \"enabled\": true,
      \"standardFlowEnabled\": true,
      \"serviceAccountsEnabled\": true,
      \"directAccessGrantsEnabled\": true,
      \"redirectUris\": [\"*\"]
    }" >/dev/null
    echo "  クライアント business-api を作成しました"
  fi

  # chat-ui用 publicクライアント (Authorization Code + PKCE)
  if [ "$(curl -sk -H "$auth_header" "${base_url}/${KEYCLOAK_REALM}/clients?clientId=chat-ui" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)" == "0" ]; then
    curl -sk -X POST "${base_url}/${KEYCLOAK_REALM}/clients" -H "$auth_header" -H "Content-Type: application/json" -d "{
      \"clientId\": \"chat-ui\",
      \"publicClient\": true,
      \"enabled\": true,
      \"standardFlowEnabled\": true,
      \"directAccessGrantsEnabled\": false,
      \"redirectUris\": [\"*\"],
      \"webOrigins\": [\"*\"],
      \"attributes\": {\"pkce.code.challenge.method\": \"S256\"}
    }" >/dev/null
    echo "  クライアント chat-ui を作成しました"
  fi

  # 初期ユーザー (Noriaki Mushino)
  local initial_username="${KEYCLOAK_INITIAL_USERNAME:-nmushino}"
  if [ "$(curl -sk -H "$auth_header" "${base_url}/${KEYCLOAK_REALM}/users?username=${initial_username}" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null)" == "0" ]; then
    curl -sk -X POST "${base_url}/${KEYCLOAK_REALM}/users" -H "$auth_header" -H "Content-Type: application/json" -d "{
      \"username\": \"${initial_username}\",
      \"firstName\": \"Noriaki\",
      \"lastName\": \"Mushino\",
      \"email\": \"${KEYCLOAK_INITIAL_USER_EMAIL:-nmushino@redhat.com}\",
      \"enabled\": true,
      \"credentials\": [{\"type\": \"password\", \"value\": \"${KEYCLOAK_INITIAL_USER_PASSWORD:-changeme123}\", \"temporary\": true}]
    }" >/dev/null
    echo "  初期ユーザー Noriaki Mushino (${initial_username}) を作成しました(初回ログイン時パスワード変更必須)"
  else
    echo "  初期ユーザー ${initial_username}: 作成済み"
  fi
}

provision_keycloak

# ===== コンテナイメージビルド (内部レジストリへバイナリビルド) =====
build_image() {
  local name=$1 context_dir=$2 dockerfile=$3
  echo "  ${name} をビルド中..."
  cat <<EOF | oc apply -f - >/dev/null
apiVersion: image.openshift.io/v1
kind: ImageStream
metadata:
  name: ${name}
  namespace: ${NAMESPACE}
---
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: ${name}
  namespace: ${NAMESPACE}
spec:
  source:
    type: Binary
    binary: {}
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: ${dockerfile}
  output:
    to:
      kind: ImageStreamTag
      name: ${name}:${ENV}
EOF
  (cd "$context_dir" && oc start-build "$name" --from-dir=. --follow -n "$NAMESPACE")
}

echo "コンテナイメージをビルド中..."
echo "  business-api を mvn package でビルド中..."
(cd backend/business-api && mvn -q -DskipTests package)
build_image business-api backend/business-api src/main/docker/Dockerfile.jvm
build_image ai-agent-orchestrator . agent/orchestrator/Dockerfile
build_image chat-ui frontend/chat-ui Dockerfile

# ===== Kafka (共有クラスタ) デプロイ =====
echo "Kafka (${KAFKA_NAMESPACE}) をデプロイ中..."
oc apply -k deployment/kustomize/kafka-shared -n "$KAFKA_NAMESPACE"

# Jobのpod templateは不変のため、完了済みJobが残っていると再apply時にkustomizeが失敗する
oc delete job qwen3-8b-model-download -n "$NAMESPACE" --ignore-not-found=true &>/dev/null

# ===== Kustomize デプロイ =====
echo "Kustomize でデプロイ中..."
oc apply -k "deployment/kustomize/overlays/${ENV}" -n "$NAMESPACE"

# chat-ui はブラウザから直接 各サービスの外部 Route を叩くため、
# Route作成後に実際のホスト名を環境変数に反映する。
# OpenMetadata/Developer Hub は同じクラスタのappsドメインを共有している前提で、
# 自クラスタのRouteホスト名からドメイン部分(先頭のroute名を除いた部分)を導出して組み立てる
AI_AGENT_ROUTE_HOST="$(oc get route ai-agent-orchestrator -n "$NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null)"
# KEYCLOAK_ROUTE_HOST は provision_keycloak() 内で既に解決済みだが、
# (レルム作成をスキップした等で)未解決の場合はここで改めて共有namespaceから取得する
if [ -z "$KEYCLOAK_ROUTE_HOST" ]; then
  KEYCLOAK_ROUTE_HOST="$(oc get route keycloak -n "$KEYCLOAK_NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null)"
fi
if [ -n "$AI_AGENT_ROUTE_HOST" ]; then
  APPS_DOMAIN="${APPS_DOMAIN:-${AI_AGENT_ROUTE_HOST#*.}}"
  OPENMETADATA_URL="${OPENMETADATA_URL:-http://openmetadata-openmetadata.${APPS_DOMAIN}/my-data}"
  DEVELOPER_HUB_URL="${DEVELOPER_HUB_URL:-https://backstage-developer-hub-quarkusdroneshop-rhdh.${APPS_DOMAIN}}"
  oc set env deployment/chat-ui -n "$NAMESPACE" \
    "API_BASE_URL=https://${AI_AGENT_ROUTE_HOST}" \
    "KEYCLOAK_URL=https://${KEYCLOAK_ROUTE_HOST}" \
    "OPENMETADATA_URL=${OPENMETADATA_URL}" \
    "DEVELOPER_HUB_URL=${DEVELOPER_HUB_URL}" >/dev/null
fi
if [ -n "$KEYCLOAK_ROUTE_HOST" ]; then
  # business-api はトークンの iss claim と一致させるため、内部Service URLではなく
  # 外部Route URLをそのままOIDC auth-server-urlとして使う
  oc patch configmap business-api-config -n "$NAMESPACE" --type merge \
    -p "{\"data\":{\"keycloak-url\":\"https://${KEYCLOAK_ROUTE_HOST}\",\"keycloak-realm\":\"${KEYCLOAK_REALM}\"}}" >/dev/null
fi

# 既存イメージタグを再利用するデプロイ済み環境では、新しいビルドを反映するためロールアウトを促す
oc rollout restart deployment/ai-agent-orchestrator -n "$NAMESPACE" 2>/dev/null || true
oc rollout restart deployment/business-api -n "$NAMESPACE" 2>/dev/null || true
oc rollout restart deployment/chat-ui -n "$NAMESPACE" 2>/dev/null || true

# ArgoCD Application 作成
if [ "$ENV" == "prod" ]; then
  oc apply -f deployment/argocd/app-of-apps.yaml -n openshift-gitops
fi

echo ""
echo "=== デプロイ完了 ==="
oc get pods -n "$NAMESPACE"
