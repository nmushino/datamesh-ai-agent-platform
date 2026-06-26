# ADR-0005: OpenMetadata をメタデータカタログとして採用

## ステータス

採用済み (2024-01-01)

## コンテキスト

AI エージェントがデータ資産を発見・管理するためのメタデータカタログを選定する。
候補: OpenMetadata, LinkedIn Datahub, Apache Atlas, Collibra (商用)

## 決定

**OpenMetadata を採用する**

## 比較

| 項目 | OpenMetadata | Datahub | Apache Atlas | Collibra |
|---|---|---|---|---|
| ライセンス | Apache 2.0 | Apache 2.0 | Apache 2.0 | 商用 |
| REST API | ✅ 充実 | ✅ | △ | ✅ |
| Python クライアント | ✅ 公式 SDK | ✅ | △ | ✅ |
| データ品質統合 | ✅ ネイティブ | △ | ❌ | ✅ |
| UI の使いやすさ | ✅ | △ | ❌ | ✅ |
| OpenShift デプロイ | ✅ | △ | △ | ❌ |
| コスト | 無料 | 無料 | 無料 | 高額 |

## 理由

1. **充実した REST API**: AI エージェントから呼び出しやすい API が揃っている
2. **公式 Python SDK**: `openmetadata-ingestion` で型安全なクライアント実装が可能
3. **データ品質統合**: テーブル品質ルールの定義・実行がネイティブ対応
4. **活発なコミュニティ**: 開発が活発でバグ修正・機能追加が迅速
5. **OpenShift 対応**: Docker イメージでのデプロイが容易

## 結果

- すべてのデータ資産は OpenMetadata に登録する
- AI Agent は `OpenMetadata Tool` 経由で OpenMetadata API を操作する
- Quarkus API からは非同期でメタデータを同期する（best-effort）
- デプロイは `deployment/openshift/openmetadata.yaml` で管理する
