#!/bin/bash
set -e

ENV=${1:-dev}
echo "=== Enterprise AI Agent Platform - Deploy to OpenShift ($ENV) ==="

# 前提確認
command -v oc &>/dev/null || { echo "oc (OpenShift CLI) が必要です"; exit 1; }
command -v mvn &>/dev/null || { echo "maven が必要です"; exit 1; }
oc whoami &>/dev/null || { echo "oc login が必要です"; exit 1; }

NAMESPACE="ai-agent-platform-${ENV}"
# Kafka(AMQ Streams)は環境間で共有し quarkusdroneshop-demo namespace に配置する
# (OpenMetadata も openmetadata namespace の既存インスタンスを共用するため、このplatformでは持たない)
KAFKA_NAMESPACE="quarkusdroneshop-demo"

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
install_operator rhbk-operator stable-v26.6 "$NAMESPACE"
install_operator amq-streams stable "$KAFKA_NAMESPACE"
# OpenShift AI (RHOAI) — Qwen3-4B を vLLM CPU (KServe) で提供するために必要
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

# ===== Kafka (共有クラスタ) デプロイ =====
echo "Kafka (${KAFKA_NAMESPACE}) をデプロイ中..."
oc apply -k deployment/kustomize/kafka-shared -n "$KAFKA_NAMESPACE"

# Jobのpod templateは不変のため、完了済みJobが残っていると再apply時にkustomizeが失敗する
oc delete job qwen3-4b-model-download -n "$NAMESPACE" --ignore-not-found=true &>/dev/null

# ===== Kustomize デプロイ =====
echo "Kustomize でデプロイ中..."
oc apply -k "deployment/kustomize/overlays/${ENV}" -n "$NAMESPACE"

# 既存イメージタグを再利用するデプロイ済み環境では、新しいビルドを反映するためロールアウトを促す
oc rollout restart deployment/ai-agent-orchestrator -n "$NAMESPACE" 2>/dev/null || true
oc rollout restart deployment/business-api -n "$NAMESPACE" 2>/dev/null || true

# ArgoCD Application 作成
if [ "$ENV" == "prod" ]; then
  oc apply -f deployment/argocd/app-of-apps.yaml -n openshift-gitops
fi

echo ""
echo "=== デプロイ完了 ==="
oc get pods -n "$NAMESPACE"
