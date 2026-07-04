# Chapter 12: Observability — 観測可能性の設計と実装

## 12.1 なぜ AI システムに観測可能性が必要か

従来のマイクロサービスと比較して、AI エージェントシステムは以下の点で**観測が難しい**:

| 課題 | 説明 |
|------|------|
| 非決定性 | 同じ入力でも LLM の出力が変わる |
| ツール連鎖 | 複数 Tool の呼び出しがネストする |
| 長期会話 | 会話状態が複数リクエストにまたがる |
| トークンコスト | LLM 呼び出しごとにコストが発生する |

本章では **Observable by Default** 原則に基づき、全レイヤーで観測可能性を確保する設計を解説する。

---

## 12.2 観測可能性の3本柱

```
┌──────────────────────────────────────────────────────────────┐
│                   OpenTelemetry Collector                     │
│         (全コンポーネントからトレース/メトリクス/ログを収集)  │
└──────────┬──────────────────┬──────────────────┬─────────────┘
           │                  │                  │
      Jaeger (分散トレース) Prometheus (メトリクス) Loki (ログ)
           │                  │                  │
           └──────────────────┴──────────────────┘
                              │
                         Grafana Dashboard
```

### Metrics (メトリクス) — Prometheus
定量的な状態を時系列で記録

### Traces (トレース) — Jaeger
リクエストの処理経路を可視化 (AI Agent → Tool → API → DB)

### Logs (ログ) — JSON 構造化ログ + Loki
全操作の証跡を残す (Audit 目的も含む)

---

## 12.3 AI Agent の計装 (Python)

### 12.3.1 OpenTelemetry セットアップ

```python
# agent/common/telemetry.py
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import os

def setup_telemetry(service_name: str = "ai-agent-orchestrator") -> None:
    resource = Resource(attributes={SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)
```

### 12.3.2 Tool 実行のトレース

```python
# tools/common/tracing.py
from opentelemetry import trace
from functools import wraps
from typing import Any, Callable

tracer = trace.get_tracer("datamesh-ai-agent-platform.tools")

def trace_tool(tool_name: str):
    """Tool 実行を自動でトレースするデコレーター。"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with tracer.start_as_current_span(f"tool.{tool_name}") as span:
                span.set_attribute("tool.name", tool_name)
                span.set_attribute("tool.args", str(kwargs))
                result = func(*args, **kwargs)
                span.set_attribute("tool.success", result.get("success", False))
                if not result.get("success"):
                    span.set_attribute("tool.error", result.get("error", ""))
                    span.set_status(trace.StatusCode.ERROR)
                return result
        return wrapper
    return decorator
```

### 12.3.3 LangGraph ステップのトレース

```python
# agent/orchestrator/graph.py (トレース付き版)
from opentelemetry import trace
from agent.common.telemetry import tracer

def intent_classification_node(state: AgentState) -> AgentState:
    with tracer.start_as_current_span("agent.intent_classification") as span:
        user_message = state["messages"][-1].content if state["messages"] else ""
        span.set_attribute("agent.input_length", len(user_message))

        intent = classify_intent(user_message)
        span.set_attribute("agent.intent", intent)

        return {**state, "intent": intent}
```

### 12.3.4 AI リクエスト専用ログフィールド

```python
# agent/common/ai_logger.py
import structlog
import time
from typing import Any

log = structlog.get_logger()

def log_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    intent: str,
    thread_id: str,
    success: bool,
    error: str = "",
) -> None:
    """LLM 呼び出しを構造化ログで記録する。コスト分析・性能分析に使用。"""
    log.info(
        "llm.call",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        latency_ms=latency_ms,
        intent=intent,
        thread_id=thread_id,
        success=success,
        error=error,
    )
```

---

## 12.4 Business API の計装 (Quarkus)

### 12.4.1 OpenTelemetry 自動計装

Quarkus の `quarkus-opentelemetry` エクステンションにより、HTTP リクエスト・DB クエリは自動でトレースされる。

```properties
# application.properties
quarkus.otel.exporter.otlp.endpoint=http://otel-collector:4317
quarkus.otel.resource.attributes=service.name=business-api,service.version=1.0.0
quarkus.log.console.format=%d{HH:mm:ss} %-5p traceId=%X{traceId} spanId=%X{spanId} [%c{2.}] %s%e%n
```

### 12.4.2 ビジネスイベントの Audit ログ

```java
// CustomerResource.java — Audit ログ付き
@POST
@RolesAllowed({"operator", "admin"})
public Response registerCustomer(CustomerRequest req) {
    var customer = service.register(req);
    log.infof("AUDIT action=customer.register customerId=%s userId=%s",
        customer.customerId, securityContext.getUserPrincipal().getName());
    return Response.status(201).entity(customer).build();
}
```

---

## 12.5 JSON 構造化ログ仕様

全コンポーネントは以下のフィールドを含む JSON ログを出力する:

```json
{
  "timestamp": "2026-06-26T10:00:00.000Z",
  "level": "INFO",
  "service": "ai-agent-orchestrator",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "thread_id": "conv-abc123",
  "user_id": "user-xyz",
  "intent": "schema_sync",
  "event": "tool.execute",
  "tool": "get_database_schema",
  "duration_ms": 142,
  "success": true
}
```

### ログレベル定義

| レベル | 用途 |
|--------|------|
| DEBUG | 開発時の詳細デバッグ情報 |
| INFO | 通常の操作記録 (Tool 実行成功、エージェント切り替え) |
| WARNING | 承認が必要な操作、パフォーマンス警告 |
| ERROR | Tool 実行失敗、LLM エラー |
| CRITICAL | システム障害、セキュリティイベント |

---

## 12.6 Prometheus メトリクス定義

### AI Agent メトリクス

```python
# agent/common/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# LLM 呼び出し回数 (model, intent, success でラベル分け)
llm_requests_total = Counter(
    "ai_agent_llm_requests_total",
    "LLM へのリクエスト総数",
    ["model", "intent", "success"]
)

# LLM レイテンシ
llm_latency_seconds = Histogram(
    "ai_agent_llm_latency_seconds",
    "LLM レスポンスレイテンシ (秒)",
    ["model", "intent"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# Tool 実行回数
tool_executions_total = Counter(
    "ai_agent_tool_executions_total",
    "Tool 実行総数",
    ["tool_name", "success"]
)

# Tool レイテンシ
tool_latency_seconds = Histogram(
    "ai_agent_tool_latency_seconds",
    "Tool 実行レイテンシ (秒)",
    ["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# アクティブ会話数
active_conversations = Gauge(
    "ai_agent_active_conversations",
    "現在進行中の会話数"
)

# Human-in-the-Loop 承認待ち数
pending_approvals = Gauge(
    "ai_agent_pending_approvals",
    "承認待ちの操作数"
)

# LLM トークン使用量 (コスト管理)
llm_tokens_total = Counter(
    "ai_agent_llm_tokens_total",
    "LLM トークン使用総数",
    ["model", "token_type"]  # token_type: prompt / completion
)
```

### Business API メトリクス (Micrometer / Quarkus)

Quarkus の `quarkus-micrometer-registry-prometheus` により以下が自動収集される:

- `http_server_requests_seconds` — HTTP リクエストレイテンシ
- `jvm_memory_used_bytes` — JVM メモリ使用量
- `hikaricp_connections_active` — DB コネクションプール状態

カスタムメトリクス:

```java
// CustomerService.java
@Inject MeterRegistry registry;

public Customer register(CustomerRequest req) {
    var timer = registry.timer("business.customer.register");
    return timer.record(() -> {
        // ... 登録処理
    });
}
```

---

## 12.7 Grafana ダッシュボード構成

### ダッシュボード 1: AI Agent Overview

| パネル | メトリクス | 説明 |
|--------|----------|------|
| リクエスト数/分 | `rate(ai_agent_llm_requests_total[5m])` | LLM 呼び出しレート |
| 平均レイテンシ | `histogram_quantile(0.95, ai_agent_llm_latency_seconds_bucket)` | P95 レイテンシ |
| Tool 成功率 | `rate(ai_agent_tool_executions_total{success="true"}[5m])` | Tool 成功率 |
| アクティブ会話 | `ai_agent_active_conversations` | リアルタイム会話数 |
| 承認待ち | `ai_agent_pending_approvals` | ヒューマンレビュー待ち |
| トークン使用量 | `rate(ai_agent_llm_tokens_total[1h])` | コスト監視 |

### ダッシュボード 2: Business API

| パネル | メトリクス |
|--------|----------|
| HTTP 成功率 | `rate(http_server_requests_seconds_count{status=~"2.."}[5m])` |
| P99 レイテンシ | `histogram_quantile(0.99, http_server_requests_seconds_bucket)` |
| DB コネクション | `hikaricp_connections_active` |
| Kafka 遅延 | `kafka_consumer_lag` |

---

## 12.8 アラートルール

```yaml
# deployment/monitoring/prometheus-rules.yaml (抜粋)
groups:
  - name: ai-agent-alerts
    rules:
      - alert: LLMHighLatency
        expr: histogram_quantile(0.95, ai_agent_llm_latency_seconds_bucket) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "LLM レスポンスが遅延しています (P95 > 10s)"

      - alert: ToolFailureRateHigh
        expr: |
          rate(ai_agent_tool_executions_total{success="false"}[5m])
          / rate(ai_agent_tool_executions_total[5m]) > 0.1
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: "Tool 失敗率が 10% を超えています"

      - alert: PendingApprovalsAccumulating
        expr: ai_agent_pending_approvals > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "承認待ち操作が積み上がっています ({{ $value }} 件)"
```

---

## 12.9 分散トレース — Jaeger での調査手順

障害発生時の調査フロー:

```
1. Grafana でエラースパイクを発見
   → エラー発生時刻を特定

2. Jaeger でその時刻の trace_id を検索
   → Service: ai-agent-orchestrator

3. トレースを開いて処理経路を確認
   → どの Tool で失敗したかを特定

4. 対象 Tool のスパンを展開
   → 入力パラメータ・エラーメッセージを確認

5. 必要に応じて structlog のログと照合
   → Loki で trace_id={値} で検索
```

---

## 12.10 コスト監視

LLM トークンコストを継続的に監視する:

```python
# agent/common/cost_tracker.py
import structlog
from agent.common.metrics import llm_tokens_total

log = structlog.get_logger()

# IBM Granite 3.0 の概算コスト (参考値)
_COST_PER_1K_TOKENS = {
    "granite-20b-code-instruct": {"prompt": 0.0002, "completion": 0.0006},
    "llama-3-70b-instruct": {"prompt": 0.0003, "completion": 0.0008},
}

def track_llm_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """LLM 呼び出しコストを記録して推定コストを返す (USD)。"""
    costs = _COST_PER_1K_TOKENS.get(model, {"prompt": 0.0005, "completion": 0.001})
    cost = (prompt_tokens / 1000 * costs["prompt"]) + \
           (completion_tokens / 1000 * costs["completion"])

    llm_tokens_total.labels(model=model, token_type="prompt").inc(prompt_tokens)
    llm_tokens_total.labels(model=model, token_type="completion").inc(completion_tokens)

    log.info("llm.cost", model=model, prompt_tokens=prompt_tokens,
             completion_tokens=completion_tokens, estimated_cost_usd=round(cost, 6))
    return cost
```
