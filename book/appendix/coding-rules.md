# Appendix: Coding Rules (詳細版)

## Python (Tool / Agent)

### ファイル構成

```python
# tools/business/customer_tools.py の標準構成

# 1. 標準ライブラリ
import os
from typing import Literal

# 2. サードパーティ
import httpx
from langchain_core.tools import tool
from pydantic import Field

# 3. 定数
BUSINESS_API_URL = os.getenv("BUSINESS_API_URL", "http://localhost:8080")
_client = httpx.Client(timeout=10.0)  # モジュールレベルで再利用

# 4. Tool 定義（1ファイルに関連する Tool をまとめる）
@tool
def register_customer(...) -> dict:
    ...

@tool
def search_customers(...) -> list[dict]:
    ...
```

### エラーハンドリングパターン

```python
# ✅ 統一エラーフォーマット
@tool
def get_customer(customer_id: str) -> dict:
    """..."""
    try:
        response = _client.get(f"{BUSINESS_API_URL}/api/v1/customers/{customer_id}")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"顧客が見つかりません: {customer_id}", "success": False}
        return {"error": f"API エラー: {e.response.status_code}", "success": False}
    except httpx.RequestError as e:
        return {"error": f"接続エラー: Business API に接続できません", "success": False}
```

### 型ヒント必須

```python
# ✅ 型ヒントを必ず付ける
def create_order_agent() -> CompiledGraph:
    ...

def route_to_agent(state: AgentState) -> str:
    ...

# ❌ 型ヒントなしは禁止
def create_order_agent():
    ...
```

---

## Java (Quarkus)

### パッケージ構成

```
com.droneplatform.{domain}/
├── {Domain}Resource.java      REST エンドポイント
├── {Domain}Service.java       ビジネスロジック
├── {Domain}Repository.java    DB アクセス (Panache)
├── {Domain}Entity.java        JPA エンティティ
├── {Domain}Request.java       リクエスト DTO
└── {Domain}Response.java      レスポンス DTO (任意)
```

### Resource の標準実装

```java
@Path("/api/v1/{domain}s")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
@RolesAllowed({"operator", "admin"})  // 必須
@Tag(name = "{Domain}", description = "...")
public class {Domain}Resource {

    @Inject {Domain}Service service;

    @GET
    @Path("/{id}")
    @Operation(summary = "取得")
    public {Domain}Entity getById(@PathParam("id") String id) {
        return service.findById(id)
            .orElseThrow(() -> new NotFoundException("{Domain} not found: " + id));
    }

    @POST
    @Operation(summary = "登録")
    public Response create(@Valid {Domain}Request request) {
        var entity = service.create(request);
        return Response.status(201).entity(entity).build();
    }
}
```

### エンティティの標準実装

```java
@Entity
@Table(name = "{domain}s")
public class {Domain}Entity extends PanacheEntityBase {

    @Id
    @Column(name = "{domain}_id", nullable = false, unique = true)
    public String id;

    @Column(nullable = false)
    public String name;

    @Column(name = "created_at", nullable = false, updatable = false)
    public Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    public Instant updatedAt = Instant.now();

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }
}
```

---

## Kafka イベント設計

### イベント命名規則

```
{domain}.{entity}.{past_tense_verb}

例:
  customer.registered
  order.status.changed
  schema.synchronized
  inventory.updated
```

### CloudEvents 形式

```json
{
  "specversion": "1.0",
  "type": "com.droneplatform.customer.registered",
  "source": "/api/v1/customers",
  "id": "uuid-v4",
  "time": "2024-01-15T10:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "customerId": "CUST-12345678",
    "name": "山田太郎",
    "registeredAt": "2024-01-15T10:30:00Z"
  }
}
```

---

## OpenMetadata Tool の FQN 形式

```
# テーブル
{service_name}.{database}.{schema}.{table}
例: postgresql-prod.dronedb.public.customers

# Kafka トピック
{service_name}.{topic}
例: kafka-prod.drone-delivery-events

# API
{service_name}.{api_collection}.{endpoint}
例: quarkus-api.customers./api/v1/customers
```

---

## Git コミットメッセージ

```
# Conventional Commits 形式
{type}({scope}): {subject}

type:
  feat     新機能
  fix      バグ修正
  docs     ドキュメントのみ
  refactor リファクタリング
  test     テスト追加・修正
  chore    ビルド・ツール変更

scope:
  tool        Tool 実装
  agent       Agent 実装
  api         Quarkus API
  deploy      デプロイ設定
  docs        ドキュメント

例:
  feat(tool): OpenMetadata lineage 取得 Tool を追加
  fix(agent): Search Agent が空クエリでクラッシュする問題を修正
  docs(chapter): chapter11 developer guide を追加
  feat(api): 注文ステータス更新エンドポイントを追加
```
