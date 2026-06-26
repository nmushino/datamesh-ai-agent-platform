# Chapter 3: Reference Architecture

## アーキテクチャ全体像

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │   Chat UI   │  │ Developer Hub    │  │ Admin Console │  │
│  │  (React)    │  │ Plugin (RHDH)    │  │               │  │
│  └──────┬──────┘  └────────┬─────────┘  └───────┬───────┘  │
└─────────┼──────────────────┼────────────────────┼──────────┘
          └──────────────────┼────────────────────┘
                             │ REST / WebSocket
┌────────────────────────────┼────────────────────────────────┐
│              AI Orchestrator Layer (OpenShift AI)            │
│                                                              │
│              Granite / Llama (vLLM)                          │
│                    ┌───────▼────────┐                        │
│                    │  Orchestrator  │                        │
│                    │  (LangGraph)   │                        │
│                    └───────┬────────┘                        │
│            ┌───────────────┼───────────────┐                 │
│            ▼               ▼               ▼                 │
│     ┌──────────┐   ┌──────────┐   ┌──────────┐              │
│     │ Schema   │   │ Search   │   │ Workflow  │  ...agents  │
│     │  Agent   │   │  Agent   │   │  Agent   │              │
│     └──────────┘   └──────────┘   └──────────┘              │
└──────────┬──────────────────────────────────┬───────────────┘
           │ Tool Call                        │ Tool Call
┌──────────▼──────────┐            ┌──────────▼──────────────┐
│  OpenMetadata Tool  │            │  Business Tool           │
│  - get_schema       │            │  - register_customer     │
│  - search_asset     │            │  - search_bom            │
│  - register_table   │            │  - update_inventory      │
│  - get_lineage      │            │  - get_order_status      │
└──────────┬──────────┘            └──────────┬──────────────┘
           │ REST API                         │ REST API
┌──────────▼──────────┐            ┌──────────▼──────────────┐
│   OpenMetadata      │            │   Quarkus Business API   │
│  (メタデータカタログ) │            │   /api/v1/*              │
└─────────────────────┘            └──────────┬──────────────┘
                                              │
                               ┌──────────────┼──────────────┐
                         ┌─────▼─────┐  ┌─────▼────┐ ┌──────▼─────┐
                         │PostgreSQL │  │  Kafka   │ │ 他システム  │
                         └───────────┘  └──────────┘ └────────────┘
```

## レイヤー責務

### Presentation Layer
- ユーザーとの対話インターフェース
- Chat UI: リアルタイムエージェント会話
- RHDH Plugin: 開発者ポータル統合

### AI Orchestrator Layer
- LangGraph によるエージェントオーケストレーション
- ユーザーの意図を解釈し、適切なエージェントに委譲
- Human-in-the-Loop 承認フロー管理

### Tool Layer
- エージェントから呼び出される関数群
- OpenMetadata Tool: メタデータ操作
- Business Tool: ビジネスロジック操作

### Business Layer
- Quarkus による REST API
- トランザクション管理、バリデーション
- Kafka イベント発行

### Infrastructure Layer
- PostgreSQL: ビジネスデータ永続化
- Kafka: 非同期イベント処理
- OpenMetadata: メタデータカタログ
- Keycloak: 認証・認可

## データフロー

### スキーマ自動登録フロー

```
1. 開発者がDBスキーマ変更をpush
2. Tekton パイプラインがスキーマ変更を検出
3. Schema Agent 起動
4. OpenMetadata Tool でスキーマ取得
5. 差分を計算
6. OpenMetadata Tool で新スキーマを登録
7. Kafka に変更イベントを発行
8. 関係者に Slack 通知
```

### メタデータ検索フロー

```
1. ユーザーが Chat UI で自然言語クエリ入力
2. Orchestrator が Search Agent に委譲
3. Search Agent が OpenMetadata Tool を呼び出し
4. OpenMetadata API でアセット検索
5. 結果をビジネスコンテキストと結合
6. ユーザーに返答
```
