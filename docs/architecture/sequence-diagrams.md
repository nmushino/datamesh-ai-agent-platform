# Sequence Diagrams

## 1. スキーマ自動登録フロー

```
開発者         Git         Tekton        Schema        OpenMetadata
  │             │           │            Agent           API
  │──push──────▶│           │              │              │
  │             │──trigger──▶│             │              │
  │             │           │──起動────────▶│             │
  │             │           │              │──get_schema──▶│
  │             │           │              │◀─schema data─│
  │             │           │              │──差分計算      │
  │             │           │              │──register────▶│
  │             │           │              │◀─registered──│
  │             │           │◀─完了────────│              │
  │◀──Slack通知─│           │              │              │
```

## 2. 自然言語メタデータ検索フロー

```
ユーザー       Chat UI    Orchestrator  Search        OpenMetadata
  │              │             │         Agent           API
  │──「顧客テーブル─▶│           │           │              │
  │  の説明は？」  │──WebSocket──▶│           │              │
  │              │             │──委譲──────▶│             │
  │              │             │             │──search──────▶│
  │              │             │             │◀─assets──────│
  │              │             │◀─回答生成───│              │
  │              │◀─回答────────│             │              │
  │◀─表示────────│             │             │              │
```

## 3. ビジネスデータ登録 + メタデータ同期フロー

```
AI Agent      Business      PostgreSQL     Kafka       OpenMetadata
  │           API              │             │            API
  │──register_customer────────▶│             │            │
  │           │──INSERT────────▶│            │            │
  │           │◀─OK─────────────│            │            │
  │           │──publish────────────────────▶│            │
  │           │──sync_metadata──────────────────────────▶│
  │           │                 │            │◀─OK────────│
  │◀─customer─│                 │            │            │
```

## 4. Human-in-the-Loop 承認フロー

```
AI Agent    LangGraph    Kafka      Slack Bot   承認者      LangGraph
  │           │            │           │           │            │
  │──高リスク操作▶│           │           │           │            │
  │           │──interrupt  │           │           │            │
  │           │──publish────▶│          │           │            │
  │           │             │──通知──────▶│          │            │
  │           │             │           │──表示──────▶│           │
  │           │             │           │           │─承認────────▶│
  │           │             │◀──approved─────────────│            │
  │           │◀──resume────│           │           │            │
  │           │──継続処理    │           │           │            │
  │◀──完了────│             │           │           │            │
```

## 5. スキーマ変更伝播フロー (Kafka)

```
Schema        Kafka        Notification   OpenMetadata   Data Quality
Agent          │           Service         API            Agent
  │──publish───▶│           │              │              │
  │             │──consume──▶│             │              │
  │             │           │──Slack通知    │              │
  │             │──consume────────────────────────────────▶│
  │             │                          │              │──validate
  │             │                          │              │──report
```
