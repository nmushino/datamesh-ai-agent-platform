# Chapter 10: Deployment (GitOps / Tekton / ArgoCD)

## GitOps 構成

```
deployment/
├── argocd/
│   ├── app-of-apps.yaml          (全アプリ管理)
│   ├── ai-agent-app.yaml         (AI エージェント)
│   ├── business-api-app.yaml     (Quarkus API)
│   └── infrastructure-app.yaml   (インフラ)
└── kustomize/
    ├── base/                     (共通設定)
    └── overlays/
        ├── dev/
        ├── staging/
        └── prod/
```

## ArgoCD App-of-Apps

```yaml
# deployment/argocd/app-of-apps.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: enterprise-ai-agent-platform
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: https://github.com/quarkusdroneshop/enterprise-ai-agent-platform
    targetRevision: main
    path: deployment/argocd
  destination:
    server: https://kubernetes.default.svc
    namespace: openshift-gitops
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

## Tekton CI/CD パイプライン

```yaml
# deployment/tekton/build-pipeline.yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: ai-agent-build-pipeline
  namespace: ai-agent-platform
  annotations:
    tekton.dev/cicd: "true"
spec:
  params:
  - name: git-url
    type: string
  - name: git-revision
    type: string
    default: main
  - name: image-name
    type: string
  tasks:
  - name: git-clone
    taskRef:
      name: git-clone
      kind: ClusterTask
    params:
    - name: url
      value: $(params.git-url)
    - name: revision
      value: $(params.git-revision)
    workspaces:
    - name: output
      workspace: shared-workspace

  - name: unit-test
    runAfter: ["git-clone"]
    taskRef:
      name: python-test
    params:
    - name: source-dir
      value: agent/
    workspaces:
    - name: source
      workspace: shared-workspace

  - name: build-image
    runAfter: ["unit-test"]
    taskRef:
      name: buildah
      kind: ClusterTask
    params:
    - name: IMAGE
      value: $(params.image-name):$(tasks.git-clone.results.commit)
    workspaces:
    - name: source
      workspace: shared-workspace

  - name: update-gitops
    runAfter: ["build-image"]
    taskRef:
      name: git-update-deployment
    params:
    - name: git-url
      value: $(params.git-url)
    - name: new-image
      value: $(params.image-name):$(tasks.git-clone.results.commit)
    - name: kustomization-path
      value: deployment/kustomize/overlays/dev
```

## Kustomize オーバーレイ

```yaml
# deployment/kustomize/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- deployment.yaml
- service.yaml
- configmap.yaml
commonLabels:
  app.kubernetes.io/name: enterprise-ai-agent-platform
  app.kubernetes.io/managed-by: argocd

---
# deployment/kustomize/overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
bases:
- ../../base
namespace: ai-agent-platform-prod
patches:
- target:
    kind: Deployment
    name: ai-agent-orchestrator
  patch: |-
    - op: replace
      path: /spec/replicas
      value: 3
    - op: replace
      path: /spec/template/spec/containers/0/resources/limits/memory
      value: "2Gi"
images:
- name: ai-agent-orchestrator
  newTag: "v1.2.0"
```

## デプロイ手順

```bash
# 1. 事前確認
oc get nodes
oc get csv -n openshift-operators | grep rhoai

# 2. 名前空間作成
oc new-project ai-agent-platform
oc label namespace ai-agent-platform argocd.argoproj.io/managed-by=openshift-gitops

# 3. Secret 作成
oc create secret generic openmetadata-secret \
  --from-literal=jwt-token="<JWT_TOKEN>" \
  -n ai-agent-platform

oc create secret generic agent-db-secret \
  --from-literal=url="postgresql://user:pass@postgresql:5432/agentdb" \
  -n ai-agent-platform

# 4. ArgoCD Application デプロイ
oc apply -f deployment/argocd/app-of-apps.yaml -n openshift-gitops

# 5. 同期確認
argocd app sync enterprise-ai-agent-platform
argocd app wait enterprise-ai-agent-platform --health
```
