# Logical Architecture

## アーキテクチャ全体図

```
┌─────────────────────────────────────────────────────────────────┐
│ Presentation Layer                                               │
│  Chat UI │ RHDH Developer Portal Plugin │ Admin Console          │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTPS / WebSocket
┌──────────────────────────────▼──────────────────────────────────┐
│ AI Orchestrator Layer                                            │
│                                                                  │
│              OpenShift AI (Granite / Llama)                      │
│                         │                                        │
│                  AI Agent (LangGraph)                            │
│                    ├── Intent Classifier                         │
│                    ├── Agent Router                              │
│                    └── Human-in-the-Loop (PostgreSQL Checkpoint) │
└───────────────┬─────────────────────────────┬────────────────────┘
                │                             │
                │ Tool Call                   │ Tool Call
┌───────────────▼───────────┐   ┌─────────────▼───────────────────┐
│ OpenMetadata Tool         │   │ Business Tool                    │
│ - get_database_schema     │   │ - register_customer              │
│ - search_data_assets      │   │ - search_customers               │
│ - register_table_metadata │   │ - register_bom                   │
│ - get_data_lineage        │   │ - search_inventory               │
│ - create_quality_rule     │   │ - update_order_status            │
└───────────────┬───────────┘   └─────────────┬───────────────────┘
                │ REST API                     │ REST API
┌───────────────▼───────────┐   ┌─────────────▼───────────────────┐
│ OpenMetadata              │   │ Quarkus Business API             │
│ (メタデータカタログ)        │   │ /api/v1/customers               │
│ - Tables / Topics / APIs  │   │ /api/v1/bom                     │
│ - Lineage / Quality       │   │ /api/v1/inventory               │
│ - Glossary / Tags         │   │ /api/v1/orders                  │
└───────────────────────────┘   └──────┬───────────┬──────┬───────┘
                                       │           │      │
                              ┌────────▼──┐  ┌─────▼──┐ ┌▼──────────┐
                              │PostgreSQL │  │ Kafka  │ │ 他システム  │
                              └───────────┘  └────────┘ └───────────┘
```

## 重要な設計ポイント

### Tool の責務分離

```
OpenMetadata Tool:
  - OpenMetadata REST API のみと通信する
  - Quarkus API / PostgreSQL には直接アクセスしない
  - メタデータの CRUD に特化

Business Tool:
  - Quarkus Business API のみと通信する
  - OpenMetadata / PostgreSQL には直接アクセスしない
  - ビジネスデータの CRUD に特化
```

### Quarkus API の役割

```
Business Tool から受け取ったリクエストを:
  1. バリデーション (Bean Validation)
  2. ビジネスロジック適用
  3. PostgreSQL への永続化
  4. Kafka へのイベント発行
  5. 他システム連携
  6. OpenMetadata へのメタデータ同期（非同期）
```

### AI Agent は API のみを知る

```
AI Agent の視点:
  - OpenMetadata Tool を呼ぶ → 結果が返ってくる
  - Business Tool を呼ぶ    → 結果が返ってくる

AI Agent が知らないこと:
  - OpenMetadata の内部実装
  - PostgreSQL のスキーマ
  - Kafka のトピック構成
  - 他システムの詳細
```

## コンポーネント間インターフェース

| 送信元 | 送信先 | プロトコル | 認証 | 用途 |
|---|---|---|---|---|
| Chat UI | AI Agent | WebSocket | JWT | リアルタイム会話 |
| RHDH Plugin | AI Agent | REST | JWT | メタデータ検索 |
| AI Agent | OpenMetadata Tool | 関数呼び出し | - | Tool 実行 |
| AI Agent | Business Tool | 関数呼び出し | - | Tool 実行 |
| OpenMetadata Tool | OpenMetadata API | REST / HTTPS | JWT | メタデータ CRUD |
| Business Tool | Quarkus API | REST / HTTPS | JWT | ビジネスデータ CRUD |
| Quarkus API | PostgreSQL | JDBC / TLS | Password | データ永続化 |
| Quarkus API | Kafka | Kafka Protocol / TLS | SASL | イベント発行 |
| Quarkus API | 他システム | REST / HTTPS | API Key | 外部連携 |

## セキュリティ境界

```
[外部ユーザー]
  ↓ HTTPS + Keycloak JWT
[Presentation Layer] ← Route + TLS 終端
  ↓ Internal Network (NetworkPolicy)
[AI Agent] ← ServiceAccount Token
  ↓ Internal Network (NetworkPolicy)
[Tool → OpenMetadata / Quarkus API] ← Secret Mount (JWT / API Key)
  ↓ Internal Network (NetworkPolicy)
[PostgreSQL / Kafka / 他システム] ← Secret Mount (Password / SASL)
```
