#!/bin/bash
set -e

ENV=${1:-dev}
echo "=== Enterprise AI Agent Platform - Deploy to OpenShift ($ENV) ==="

# 前提確認
command -v oc &>/dev/null || { echo "oc (OpenShift CLI) が必要です"; exit 1; }
oc whoami &>/dev/null || { echo "oc login が必要です"; exit 1; }

NAMESPACE="ai-agent-platform-${ENV}"

# Namespace 作成
oc get namespace "$NAMESPACE" &>/dev/null || oc new-project "$NAMESPACE"
oc label namespace "$NAMESPACE" argocd.argoproj.io/managed-by=openshift-gitops --overwrite

# Secret 作成 (初回のみ)
if [ "$2" == "--init-secrets" ]; then
  echo "Secret を作成中..."
  oc create secret generic openmetadata-secret \
    --from-literal=jwt-token="${OPENMETADATA_JWT_TOKEN}" \
    -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -

  oc create secret generic agent-db-secret \
    --from-literal=url="${AGENT_DB_URL}" \
    -n "$NAMESPACE" --dry-run=client -o yaml | oc apply -f -
fi

# Kustomize デプロイ
echo "Kustomize でデプロイ中..."
oc apply -k "deployment/kustomize/overlays/${ENV}" -n "$NAMESPACE"

# ArgoCD Application 作成
if [ "$ENV" == "prod" ]; then
  oc apply -f deployment/argocd/app-of-apps.yaml -n openshift-gitops
fi

echo ""
echo "=== デプロイ完了 ==="
oc get pods -n "$NAMESPACE"
