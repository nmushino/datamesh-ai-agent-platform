# Enterprise AI Agent Platform

OpenShift AI 上で動作する、OpenMetadata を中心としたエンタープライズ AI エージェントプラットフォームです。

## アーキテクチャ概要

```
            OpenShift AI
          (Granite / Llama)
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

# デプロイ
./scripts/deploy.sh
```
