# Chapter 9: OpenShift AI デプロイ

## OpenShift AI コンポーネント構成

```
OpenShift AI (RHOAI)
├── ServingRuntime: vLLM
│   └── InferenceService: granite-20b-code-instruct
├── DataScienceProject: ai-agent-platform
│   ├── Workbench: agent-development
│   └── PipelineServer: elyra-pipelines
└── ModelRegistry: (モデル管理)
```

## vLLM InferenceService

```yaml
# deployment/openshift/vllm-serving.yaml
apiVersion: serving.kserve.io/v1alpha1
kind: ServingRuntime
metadata:
  name: vllm-runtime
  namespace: ai-agent-platform
spec:
  containers:
  - name: kserve-container
    image: quay.io/rh-aiservices-bu/vllm-openai-ubi9:0.4.2
    command: ["python", "-m", "vllm.entrypoints.openai.api_server"]
    args:
    - "--model=/mnt/models"
    - "--dtype=float16"
    - "--max-model-len=8192"
    resources:
      requests:
        cpu: "4"
        memory: "16Gi"
        nvidia.com/gpu: "1"
      limits:
        cpu: "8"
        memory: "32Gi"
        nvidia.com/gpu: "1"
---
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: granite-20b-code-instruct
  namespace: ai-agent-platform
  annotations:
    serving.knative.openshift.io/enablePassthrough: "true"
    sidecar.istio.io/inject: "true"
spec:
  predictor:
    model:
      modelFormat:
        name: vLLM
      runtime: vllm-runtime
      storageUri: "pvc://model-storage/granite-20b-code-instruct"
```

## AI Agent デプロイ

```yaml
# deployment/openshift/agent-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-agent-orchestrator
  namespace: ai-agent-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ai-agent-orchestrator
  template:
    metadata:
      labels:
        app: ai-agent-orchestrator
    spec:
      containers:
      - name: orchestrator
        image: quay.io/droneplatform/ai-agent-orchestrator:latest
        ports:
        - containerPort: 8000
        env:
        - name: VLLM_BASE_URL
          value: "http://granite-20b-code-instruct-predictor:8080/v1"
        - name: OPENMETADATA_HOST
          value: "http://openmetadata:8585"
        - name: BUSINESS_API_URL
          value: "http://business-api:8080"
        - name: KAFKA_BOOTSTRAP_SERVERS
          value: "kafka:9092"
        - name: POSTGRES_URL
          valueFrom:
            secretKeyRef:
              name: agent-db-secret
              key: url
        - name: OPENMETADATA_JWT_TOKEN
          valueFrom:
            secretKeyRef:
              name: openmetadata-secret
              key: jwt-token
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: ai-agent-orchestrator
  namespace: ai-agent-platform
spec:
  selector:
    app: ai-agent-orchestrator
  ports:
  - port: 8000
    targetPort: 8000
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: ai-agent-orchestrator
  namespace: ai-agent-platform
spec:
  to:
    kind: Service
    name: ai-agent-orchestrator
  tls:
    termination: edge
```

## NetworkPolicy

```yaml
# deployment/openshift/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: agent-network-policy
  namespace: ai-agent-platform
spec:
  podSelector:
    matchLabels:
      app: ai-agent-orchestrator
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: chat-ui
    ports:
    - port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: openmetadata
    ports:
    - port: 8585
  - to:
    - podSelector:
        matchLabels:
          app: business-api
    ports:
    - port: 8080
  - to:
    - podSelector:
        matchLabels:
          app: kafka
    ports:
    - port: 9092
```
