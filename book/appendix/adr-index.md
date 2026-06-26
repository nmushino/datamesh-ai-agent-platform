# Appendix: ADR Index (アーキテクチャ決定記録 一覧)

## 決定済み ADR

| ID | タイトル | ステータス | 決定日 | 概要 |
|---|---|---|---|---|
| [ADR-0001](../../docs/adr/0001-tool-first.md) | Tool-First アーキテクチャの採用 | 採用済み | 2024-01-01 | すべての外部操作を @tool で定義する |
| [ADR-0002](../../docs/adr/0002-metadata-first.md) | Metadata-First アーキテクチャの採用 | 採用済み | 2024-01-01 | OpenMetadata を SoT とする |
| [ADR-0003](../../docs/adr/0003-langgraph.md) | LangGraph の採用 | 採用済み | 2024-01-01 | CrewAI/AutoGen より LangGraph を選択 |
| [ADR-0004](../../docs/adr/0004-quarkus.md) | Quarkus Business API の採用 | 採用済み | 2024-01-01 | Spring Boot より Quarkus を選択 |
| [ADR-0005](../../docs/adr/0005-openmetadata.md) | OpenMetadata の採用 | 採用済み | 2024-01-01 | Datahub/Apache Atlas より OpenMetadata を選択 |
| [ADR-0006](../../docs/adr/0006-openshift-ai.md) | OpenShift AI の採用 | 採用済み | 2024-01-01 | セルフホスト LLM 基盤として RHOAI を選択 |

## ADR 作成ガイドライン

新しいアーキテクチャ決定が必要な場合は、以下のテンプレートで `docs/adr/000N-title.md` を作成してください。

```markdown
# ADR-000N: タイトル

## ステータス
提案中 / 採用済み / 廃止

## コンテキスト
なぜこの決定が必要になったか

## 決定
何を決定したか

## 理由
なぜこの選択をしたか（代替案との比較を含む）

## 結果
この決定がもたらす影響・制約

## トレードオフ
| 利点 | 欠点 |
|---|---|
| ... | ... |
```

## ADR が必要なケース

- フレームワーク・ライブラリの選定
- 通信プロトコルの変更
- データストアの選定
- セキュリティ方針の変更
- 既存 ADR の撤回・変更
