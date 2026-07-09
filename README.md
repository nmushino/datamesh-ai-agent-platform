# Datamesh AI Agent Platform

OpenShift AI 上で動作する、OpenMetadata を中心としたエンタープライズ AI エージェントプラットフォームです。

## アーキテクチャ概要

```
            OpenShift AI
          (Qwen3 / Llama)
                 │
          AI Agent (LangGraph)
                 │
  ┌──────────────┴──────────────┐
  │                             │
OpenMetadata Tool         Business Tool
  │                             │
REST API                   REST API
  │                             │
OpenMetadata             Quarkus API
                               │
              ┌────────────────┼──────────────┐
              │                │              │
          PostgreSQL         Kafka        他システム
```

## 主要ユースケース

| ユースケース | 説明 |
|---|---|
| スキーマ自動登録 | DB スキーマ・API スペックを OpenMetadata に自動登録 |
| メタデータ検索 | 自然言語で OpenMetadata のアセットを検索・取得 |
| ビジネスデータ登録 | 顧客・BOM 等のビジネスデータをメタデータと紐付けて登録 |
| データ品質管理 | データ品質ルールの自動設定・検証 |

## 技術スタック

| レイヤー | 技術 |
|---|---|
| AI 基盤 | OpenShift AI, vLLM, IBM Granite |
| エージェント | LangGraph (Python) |
| バックエンド | Quarkus (Java) |
| メタデータ | OpenMetadata |
| メッセージング | Apache Kafka |
| データベース | PostgreSQL |
| ID 管理 | Keycloak |
| デプロイ | OpenShift, ArgoCD, Tekton |

## ドキュメント

- [book/](book/) — 詳細設計ドキュメント (全17章)
- [docs/architecture/](docs/architecture/) — アーキテクチャ設計
- [docs/implementation/](docs/implementation/) — 実装ガイド
- [docs/deployment/](docs/deployment/) — デプロイ手順
- [docs/adr/](docs/adr/) — アーキテクチャ決定記録

## クイックスタート

```bash
# 開発環境起動
./scripts/dev.sh

# chat-ui のみローカルで起動 (画面開発用、Keycloak認証は自動でスキップ)
./scripts/chat-ui.sh

# デプロイ
./scripts/deploy.sh
```

## Bug List

LangGraphの入れ子実行(グラフの中でさらに別のコンパイル済みグラフを呼び出す)自体にバグがあるため、stream()/.invoke()どちらでも、外側グラフ経由でノード関数を実行すると必ず失敗する。代わりにそのままPython関数として直接呼んだ場合は毎回成功する。これはcreate_react_agentが内部でコンパイル済みグラフを作る仕組みのため、サブエージェントをLangGraphの外側グラフの中で使う限り避けられないことがわかっている。対策として、サブエージェントのツール呼び出しループをLangGraphのネストしたグラフを使わず、LLM+ツールバインディングによる手動ループに置き換えることで回避する。

---

# Datamesh AI Agent Platform

An enterprise AI agent platform centered on OpenMetadata, running on OpenShift AI.

## Architecture Overview

```
            OpenShift AI
          (Qwen3 / Llama)
                 │
          AI Agent (LangGraph)
                 │
  ┌──────────────┴──────────────┐
  │                             │
OpenMetadata Tool         Business Tool
  │                             │
REST API                   REST API
  │                             │
OpenMetadata             Quarkus API
                               │
              ┌────────────────┼──────────────┐
              │                │              │
          PostgreSQL         Kafka        Other Systems
```

## Key Use Cases

| Use Case | Description |
|---|---|
| Automatic schema registration | Automatically register DB schemas and API specs into OpenMetadata |
| Metadata search | Search and retrieve OpenMetadata assets using natural language |
| Business data registration | Register business data (customers, BOM, etc.) linked to metadata |
| Data quality management | Automatically configure and validate data quality rules |

## Technology Stack

| Layer | Technology |
|---|---|
| AI Platform | OpenShift AI, vLLM, IBM Granite |
| Agent | LangGraph (Python) |
| Backend | Quarkus (Java) |
| Metadata | OpenMetadata |
| Messaging | Apache Kafka |
| Database | PostgreSQL |
| Identity Management | Keycloak |
| Deployment | OpenShift, ArgoCD, Tekton |

## Documentation

- [book/](book/) — Detailed design documentation (17 chapters)
- [docs/architecture/](docs/architecture/) — Architecture design
- [docs/implementation/](docs/implementation/) — Implementation guide
- [docs/deployment/](docs/deployment/) — Deployment instructions
- [docs/adr/](docs/adr/) — Architecture decision records

## Quick Start

```bash
# Start the development environment
./scripts/dev.sh

# Run chat-ui locally only (for UI development, Keycloak auth is skipped automatically)
./scripts/chat-ui.sh

# Deploy
./scripts/deploy.sh
```

