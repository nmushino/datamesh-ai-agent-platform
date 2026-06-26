# Chapter 4: Platform Architecture

## 概要

本章では、AI エージェントプラットフォームを支える **プラットフォーム基盤** の詳細設計を説明します。OpenShift AI を中心に、各コンポーネントがどのように連携するかを定義します。

---

## プラットフォーム全体構成

```
┌─────────────────────────────────────────────────────────────────────┐
│                     OpenShift Platform (4.14+)                       │
│                                                                       │
│  Namespace: ai-agent-platform                                         │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                  OpenShift AI (RHOAI)                         │    │
│  │  ┌─────────────────┐  ┌──────────────────────────────────┐   │    │
│  │  │  Model Serving  │  │  DataScience Project             │   │    │
│  │  │  ┌───────────┐  │  │  ┌─────────────────────────────┐ │   │    │
│  │  │  │ vLLM      │  │  │  │ Workbench (JupyterLab)      │ │   │    │
│  │  │  │ Granite   │  │  │  └─────────────────────────────┘ │   │    │
│  │  │  │ Llama     │  │  │  ┌─────────────────────────────┐ │   │    │
│  │  │  └───────────┘  │  │  │ Pipeline Server (Elyra)     │ │   │    │
│  │  └─────────────────┘  │  └─────────────────────────────┘ │   │    │
│  │                        └──────────────────────────────────┘   │    │
│  │                                                               │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │    │
│  │  │ AI Agent    │  │ Business API  │  │ OpenMetadata       │  │    │
│  │  │ (LangGraph) │  │ (Quarkus)    │  │ (メタデータカタログ) │  │    │
│  │  └─────────────┘  └──────────────┘  └────────────────────┘  │    │
│  │                                                               │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │    │
│  │  │ Chat UI     │  │ PostgreSQL   │  │ AMQ Streams (Kafka) │  │    │
│  │  │ (React)     │  │             │  │                    │  │    │
│  │  └─────────────┘  └──────────────┘  └────────────────────┘  │    │
│  │                                                               │    │
│  │  ┌─────────────┐  ┌──────────────┐                          │    │
│  │  │ Keycloak    │  │ RHDH         │                          │    │
│  │  │ (IdP)       │  │ (Dev Portal) │                          │    │
│  │  └─────────────┘  └──────────────┘                          │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Platform Services                                            │    │
│  │  OpenShift GitOps (ArgoCD) │ OpenShift Pipelines (Tekton)    │    │
│  │  OpenShift Monitoring      │ OpenShift Logging               │    │
│  └──────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## OpenShift AI (RHOAI) コンポーネント

### Model Serving

```yaml
# ServingRuntime: vLLM (OpenAI API 互換)
モデル: IBM Granite 20B Code Instruct / Meta Llama 3 8B Instruct
GPU: NVIDIA A100 (1枚/推論サービス)
エンドポイント: http://vllm-service/v1 (OpenAI API 互換)

# AI Agent からの呼び出し例
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    base_url="http://granite-predictor/v1",
    model="ibm-granite-20b-code-instruct"
)
```

### モデル選定指針

| ユースケース | 推奨モデル | 理由 |
|---|---|---|
| コード生成・スキーマ分析 | Granite 20B Code Instruct | コード特化、日本語対応 |
| 汎用会話・メタデータ説明 | Llama 3 8B Instruct | 軽量、高速レスポンス |
| 複雑な推論・計画 | Granite 34B (将来) | 高精度 |

---

## ネットワーク構成

### Service 間通信

```
Chat UI
  ↓ Route (HTTPS / TLS 終端)
AI Agent :8000
  ↓ Service (HTTP 内部)
  ├── OpenMetadata Tool → OpenMetadata :8585
  └── Business Tool     → Quarkus API :8080
                            ↓ Service (内部)
                            ├── PostgreSQL :5432
                            ├── Kafka :9092
                            └── 外部システム (egress)
```

### NetworkPolicy 一覧

```yaml
# ai-agent は Chat UI / RHDH からのみ受信
ai-agent-ingress:
  from: [chat-ui, rhdh-backend]
  ports: [8000]

# ai-agent から OpenMetadata と Quarkus への送信のみ許可
ai-agent-egress:
  to: [openmetadata, business-api]
  ports: [8585, 8080]

# Quarkus から PostgreSQL / Kafka への送信のみ許可
business-api-egress:
  to: [postgresql, kafka]
  ports: [5432, 9092]
```

---

## ストレージ構成

| コンポーネント | PVC サイズ | StorageClass | 用途 |
|---|---|---|---|
| vLLM モデル | 100Gi | ocs-storagecluster-ceph-rbd | モデルウェイト |
| PostgreSQL | 50Gi | ocs-storagecluster-ceph-rbd | ビジネスデータ |
| OpenMetadata | 20Gi | ocs-storagecluster-ceph-rbd | メタデータ |
| Kafka | 100Gi × 3 | ocs-storagecluster-ceph-rbd | メッセージ |
| LangGraph Checkpoint | PostgreSQL 共有 | - | 会話状態 |

---

## 可観測性 (Observability)

### メトリクス (Prometheus / Grafana)

```yaml
監視対象メトリクス:
  AI Agent:
    - agent_requests_total (total/success/failure)
    - agent_latency_seconds (p50/p95/p99)
    - tool_calls_total (tool別)
    - llm_tokens_used_total

  Quarkus API:
    - http_server_requests_seconds
    - quarkus_datasource_jdbc_connections_active
    - kafka_producer_record_send_total

  OpenMetadata:
    - openmetadata_api_latency
    - openmetadata_entities_total

  vLLM:
    - vllm_requests_running
    - vllm_gpu_cache_usage_perc
    - vllm_time_to_first_token_seconds
```

### ログ (OpenShift Logging / Loki)

```python
# 構造化ログ: JSON 形式で出力
import structlog

log = structlog.get_logger()

def execute_tool(tool_name: str, args: dict):
    log.info(
        "tool_execution_started",
        tool=tool_name,
        args=args,
        thread_id=current_thread_id(),
        user=current_user(),
    )
    result = tool_fn(**args)
    log.info(
        "tool_execution_completed",
        tool=tool_name,
        success=True,
        duration_ms=elapsed_ms(),
    )
    return result
```

### 分散トレーシング (OpenTelemetry / Jaeger)

```
Chat UI → [trace: req-001] → AI Agent
                              ↓ [span: intent-classify]
                              ↓ [span: schema-agent]
                                  ↓ [span: tool:get_schema]
                                      ↓ [span: http:openmetadata]
```

---

## スケーリング戦略

### Horizontal Pod Autoscaler (HPA)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ai-agent-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ai-agent-orchestrator
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: agent_requests_in_flight
      target:
        type: AverageValue
        averageValue: "5"
```

### vLLM スケーリング

```
vLLM はステートフルなため、HPA ではなく手動スケール。
GPU 使用率 80% 超で追加 GPU ノードのスケジューリングを検討。

# GPU ノード確認
oc get nodes -l node-role.kubernetes.io/gpu=true
```

---

## 障害対応設計

### コンポーネント障害時の挙動

| 障害コンポーネント | AI Agent の挙動 | ユーザーへの影響 |
|---|---|---|
| vLLM | エラー返却、リトライなし | 操作不可（ユーザーに通知） |
| OpenMetadata | OpenMetadata Tool がエラー返却 | メタデータ操作のみ不可 |
| Quarkus API | Business Tool がエラー返却 | ビジネスデータ操作のみ不可 |
| PostgreSQL | Quarkus API がエラー返却 | 書き込み操作のみ不可 |
| Kafka | 書き込み成功、イベント未発行 | 通知・非同期処理が遅延 |

### LangGraph チェックポイントによる再開

```python
# PostgreSQL が復旧後、中断した会話を再開できる
config = {"configurable": {"thread_id": "abc-123"}}
state = graph.get_state(config)
# → 中断時点の状態から再開可能
result = graph.invoke(None, config)
```
