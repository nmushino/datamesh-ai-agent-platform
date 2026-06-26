# Project Context for Claude

## プロジェクト概要

OpenShift AI 上で動作する、OpenMetadata を中核とした AI エージェント自動化プラットフォーム。

## アーキテクチャ原則

1. **Tool-First**: すべての外部操作は Tool として実装する (ADR-0001)
2. **Metadata-First**: OpenMetadata を Single Source of Truth とする (ADR-0002)
3. **LangGraph**: エージェントオーケストレーションに使用 (ADR-0003)
4. **Human-in-the-Loop**: 破壊的操作は必ず承認を取る

## ディレクトリ構造

```
agent/           - LangGraph エージェント (Python)
tools/           - Tool 実装 (Python)
backend/         - Quarkus Business API (Java)
frontend/        - Chat UI / RHDH Plugin (React)
prompts/         - システムプロンプト (Markdown)
deployment/      - OpenShift / Tekton / ArgoCD
docs/            - アーキテクチャ・実装ドキュメント
book/            - 詳細設計ドキュメント
```

## 技術スタック

- AI: OpenShift AI + vLLM + IBM Granite
- エージェント: LangGraph (Python 3.11)
- API: Quarkus 3.x (Java 21)
- メタデータ: OpenMetadata 1.3.x
- メッセージング: Apache Kafka (AMQ Streams)
- DB: PostgreSQL 15
- 認証: Keycloak
- デプロイ: OpenShift 4.14 + ArgoCD + Tekton

## 命名規則

- Python: snake_case (関数・変数), PascalCase (クラス)
- Java: camelCase (メソッド), PascalCase (クラス)
- Tool名: snake_case, 動詞_名詞形式 (例: register_customer)
- Kubernetes: kebab-case
- Kafka トピック: kebab-case

## 重要な設計決定

- Tool は冪等に設計する
- 破壊的操作は `requires_approval: True` を必ず設定
- OpenMetadata 同期失敗はビジネス処理を止めない (best-effort)
- エラーメッセージは日本語でユーザーに返す
