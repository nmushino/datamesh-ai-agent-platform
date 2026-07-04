# Chapter 11: Developer Guide

## 開発環境セットアップ

### 前提条件

```bash
# 必須ツール確認
python --version    # 3.11+
java --version      # 21+
mvn --version       # 3.9+
node --version      # 20+
docker --version    # 24+
oc version          # 4.14+
```

### ローカル開発環境起動

```bash
# 1. リポジトリ取得
git clone https://github.com/quarkusdroneshop/datamesh-ai-agent-platform
cd datamesh-ai-agent-platform

# 2. 環境変数設定
cp .env.example .env
# .env を編集してトークン等を設定

# 3. 開発環境一括起動
./scripts/dev.sh
```

### `.env.example`

```bash
# OpenMetadata
OPENMETADATA_HOST=http://localhost:8585
OPENMETADATA_JWT_TOKEN=<generate_from_openmetadata_ui>

# vLLM (ローカルは ollama 互換で代替可能)
VLLM_BASE_URL=http://localhost:11434/v1
VLLM_MODEL=ibm-granite-20b-code-instruct

# Quarkus API
BUSINESS_API_URL=http://localhost:8080

# DB (LangGraph チェックポイント用)
AGENT_DB_URL=postgresql://postgres:postgres@localhost:5432/agentdb

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

---

## Tool の開発手順

### 新しい Tool を追加する

```bash
# 1. Tool ファイルを作成
touch tools/business/order_tools.py

# 2. テストファイルを作成
touch tests/integration/test_order_tools.py
```

```python
# tools/business/order_tools.py

from langchain_core.tools import tool
import httpx
import os

BUSINESS_API_URL = os.getenv("BUSINESS_API_URL", "http://localhost:8080")

@tool
def get_order_status(order_id: str) -> dict:
    """
    注文の現在ステータスを取得します。

    Args:
        order_id: 注文 ID (形式: ORD-XXXXXXXX)

    Returns:
        注文ステータス情報の辞書
        {
          "orderId": str,
          "status": "PENDING" | "PROCESSING" | "DELIVERED" | "CANCELLED",
          "updatedAt": str (ISO 8601)
        }

    Raises:
        ToolException: 注文が存在しない場合、または API 接続失敗時
    """
    try:
        response = httpx.get(
            f"{BUSINESS_API_URL}/api/v1/orders/{order_id}",
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"注文が見つかりません: {order_id}", "success": False}
        raise
    except httpx.RequestError as e:
        return {"error": f"API 接続エラー: {str(e)}", "success": False}


@tool
def update_order_status(
    order_id: str,
    new_status: str,
    reason: str = ""
) -> dict:
    """
    注文ステータスを更新します。

    Args:
        order_id: 注文 ID
        new_status: 新しいステータス ("PROCESSING", "DELIVERED", "CANCELLED")
        reason: ステータス変更の理由（任意）

    Returns:
        更新された注文情報

    Note:
        CANCELLED への変更は requires_approval フラグが自動的に True になります。
    """
    payload = {"status": new_status, "reason": reason}
    response = httpx.patch(
        f"{BUSINESS_API_URL}/api/v1/orders/{order_id}/status",
        json=payload,
        timeout=10.0
    )
    response.raise_for_status()
    return response.json()
```

### Tool のテスト

```python
# tests/integration/test_order_tools.py

import pytest
from unittest.mock import patch, MagicMock
from tools.business.order_tools import get_order_status, update_order_status

class TestGetOrderStatus:
    def test_existing_order(self, mock_api):
        """正常系: 存在する注文を取得できる"""
        mock_api.return_value.json.return_value = {
            "orderId": "ORD-12345678",
            "status": "PROCESSING",
            "updatedAt": "2024-01-15T10:30:00Z"
        }

        result = get_order_status.invoke({"order_id": "ORD-12345678"})

        assert result["orderId"] == "ORD-12345678"
        assert result["status"] == "PROCESSING"

    def test_not_found_order(self, mock_api_404):
        """注文が存在しない場合はエラーメッセージを返す"""
        result = get_order_status.invoke({"order_id": "ORD-NOTEXIST"})

        assert result["success"] is False
        assert "見つかりません" in result["error"]

# pytest で実行
# pytest tests/integration/test_order_tools.py -v
```

---

## Agent の開発手順

### 新しい Agent を追加する

```bash
mkdir -p agent/order-agent
touch agent/order-agent/{__init__.py,agent.py,graph.py}
touch prompts/order/system.md
```

```python
# agent/order-agent/agent.py

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from tools.business.order_tools import get_order_status, update_order_status
from tools.openmetadata.schema_tools import search_data_assets
import os

def create_order_agent():
    llm = ChatOpenAI(
        base_url=os.getenv("VLLM_BASE_URL"),
        model=os.getenv("VLLM_MODEL"),
        api_key="not-needed",
        temperature=0,         # 一貫性のある出力のため 0 を推奨
        max_tokens=1024,
    )

    # system prompt は外部ファイルから読み込む
    with open("prompts/order/system.md") as f:
        system_prompt = f.read()

    tools = [
        get_order_status,
        update_order_status,
        search_data_assets,  # 注文関連メタデータ検索
    ]

    return create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=system_prompt,
    )
```

```markdown
<!-- prompts/order/system.md -->

あなたは注文管理の専門 AI エージェントです。

## 役割
- 注文ステータスの確認・更新
- 注文に関するメタデータの検索
- 注文処理に関する質問への回答

## 制約
- CANCELLED への変更は必ず理由を確認してから実行する
- 個人情報（顧客名・住所）は回答に含めない
- 不明な場合は推測せず「確認が必要です」と答える

## 応答形式
- 日本語で回答する
- 簡潔に、重要な情報を最初に述べる
```

### Orchestrator への登録

```python
# agent/orchestrator/router.py に追記

from agent.order_agent.agent import create_order_agent

AGENT_REGISTRY = {
    "schema":       create_schema_agent,
    "search":       create_search_agent,
    "registration": create_registration_agent,
    "order":        create_order_agent,       # ← 追加
}

INTENT_TO_AGENT = {
    "schema_sync":      "schema",
    "metadata_search":  "search",
    "data_register":    "registration",
    "order_status":     "order",              # ← 追加
    "order_update":     "order",              # ← 追加
}
```

---

## Quarkus API の開発手順

### 新しいエンドポイントを追加する

```bash
# 1. パッケージ作成
mkdir -p backend/business-api/src/main/java/com/droneplatform/order

# 2. ファイル作成
touch backend/business-api/src/main/java/com/droneplatform/order/{OrderResource.java,OrderService.java,OrderEntity.java,OrderRequest.java}
```

```java
// backend/business-api/src/main/java/com/droneplatform/order/OrderResource.java

@Path("/api/v1/orders")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
@RolesAllowed({"operator", "admin"})
public class OrderResource {

    @Inject OrderService orderService;
    @Inject MetadataSyncService metadataSync;
    @Inject AgentEventProducer eventProducer;

    @GET
    @Path("/{orderId}")
    public Order getOrder(@PathParam("orderId") String orderId) {
        return orderService.findById(orderId)
            .orElseThrow(() -> new NotFoundException("Order not found: " + orderId));
    }

    @PATCH
    @Path("/{orderId}/status")
    @Operation(summary = "注文ステータス更新")
    public Response updateStatus(
        @PathParam("orderId") String orderId,
        @Valid StatusUpdateRequest request
    ) {
        Order updated = orderService.updateStatus(orderId, request.status(), request.reason());

        // Kafka にイベント発行
        eventProducer.sendOrderStatusChanged(updated);

        // OpenMetadata に統計を同期（非同期）
        metadataSync.syncOrderMetrics();

        return Response.ok(updated).build();
    }
}
```

### Quarkus Dev モードでのテスト

```bash
cd backend/business-api
mvn quarkus:dev

# Swagger UI: http://localhost:8080/q/swagger-ui
# Dev UI:     http://localhost:8080/q/dev/

# テスト実行
mvn test -Dquarkus.test.profile=test
```

---

## デバッグ・トラブルシューティング

### AI Agent のデバッグ

```python
# LangGraph のステップごとの出力を確認
from langgraph.graph import StateGraph

config = {"configurable": {"thread_id": "debug-001"}, "recursion_limit": 10}

# ストリーミングでステップを追跡
for event in graph.stream(
    {"messages": [("user", "顧客テーブルのスキーマを同期して")]},
    config=config,
    stream_mode="values"
):
    print(f"Step: {event}")

# チェックポイントの確認
snapshots = list(graph.get_state_history(config))
for snapshot in snapshots:
    print(f"Step {snapshot.config}: {snapshot.values['messages'][-1]}")
```

### Tool 呼び出しのログ確認

```bash
# OpenShift 上でのログ確認
oc logs -n ai-agent-platform deployment/ai-agent-orchestrator -f | \
  jq 'select(.event == "tool_execution_completed")'

# ローカルでの確認
export LOG_LEVEL=DEBUG
python -m agent.orchestrator.main
```

### よくあるエラーと対処

| エラー | 原因 | 対処 |
|---|---|---|
| `OpenMetadataNotFoundError` | FQN が間違っている | OpenMetadata UI で FQN を確認 |
| `httpx.ConnectError` | Quarkus API が起動していない | `./scripts/dev.sh` を確認 |
| `RecursionLimitError` | Agent がループしている | system prompt を見直す、recursion_limit を下げる |
| `NodeInterrupt` | Human-in-the-Loop 待ち | 正常動作。Slack で承認する |
| `JWT expired` | OpenMetadata トークン期限切れ | `.env` の JWT_TOKEN を更新 |
