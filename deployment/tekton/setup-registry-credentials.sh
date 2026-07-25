#!/usr/bin/env bash
# ai-agent-cicd の Pipeline (buildah タスク) が内部レジストリへイメージを push するために
# 必要な Secret `internal-registry-credentials` を作成する。
#
# 背景: buildah タスクの docker-credentials ワークスペースがこの Secret を要求するが、
# 存在しないと build-image TaskRun の Pod が FailedMount のままスタックし続け、
# 最終的に PipelineRun がタイムアウト/キャンセルされる (git-clone/lint/unit-test は
# 成功するのに build-image だけ進まない、という形で観測される)。
#
# Pipeline (Tekton の Pipeline/Trigger 一式) を新規登録・再登録する際は必ず本スクリプトも
# 一緒に実行すること。
set -euo pipefail

CICD_NAMESPACE="${CICD_NAMESPACE:-ai-agent-cicd}"
TARGET_NAMESPACE="${TARGET_NAMESPACE:-ai-agent-platform}"
SA_NAME="${SA_NAME:-pipeline}"
SECRET_NAME="internal-registry-credentials"
REGISTRY_HOST="image-registry.openshift-image-registry.svc:5000"

echo "--> ${CICD_NAMESPACE} の ServiceAccount '${SA_NAME}' に ${TARGET_NAMESPACE} への push 権限を付与"
oc policy add-role-to-user system:image-builder \
  "system:serviceaccount:${CICD_NAMESPACE}:${SA_NAME}" \
  -n "${TARGET_NAMESPACE}"

echo "--> ${SA_NAME} 用の長期トークンを発行し、${SECRET_NAME} Secret を作成"
TOKEN=$(oc create token "${SA_NAME}" -n "${CICD_NAMESPACE}" --duration=87600h)

oc create secret docker-registry "${SECRET_NAME}" \
  --docker-server="${REGISTRY_HOST}" \
  --docker-username=serviceaccount \
  --docker-password="${TOKEN}" \
  --docker-email=unused@example.com \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | oc apply -f -

echo "--> 完了: ${CICD_NAMESPACE}/${SECRET_NAME}"
