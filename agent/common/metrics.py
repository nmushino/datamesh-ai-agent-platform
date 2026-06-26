"""Prometheus メトリクス定義 — chapter12-observability.md の実装。"""
from prometheus_client import Counter, Gauge, Histogram

llm_requests_total = Counter(
    "ai_agent_llm_requests_total",
    "LLM へのリクエスト総数",
    ["model", "intent", "success"],
)

llm_latency_seconds = Histogram(
    "ai_agent_llm_latency_seconds",
    "LLM レスポンスレイテンシ (秒)",
    ["model", "intent"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

llm_tokens_total = Counter(
    "ai_agent_llm_tokens_total",
    "LLM トークン使用総数",
    ["model", "token_type"],
)

tool_executions_total = Counter(
    "ai_agent_tool_executions_total",
    "Tool 実行総数",
    ["tool_name", "success"],
)

tool_latency_seconds = Histogram(
    "ai_agent_tool_latency_seconds",
    "Tool 実行レイテンシ (秒)",
    ["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

active_conversations = Gauge(
    "ai_agent_active_conversations",
    "現在進行中の会話数",
)

pending_approvals = Gauge(
    "ai_agent_pending_approvals",
    "承認待ちの操作数",
)
