# Chapter 0: Executive Summary

## プロジェクト概要

本プロジェクトは、OpenShift AI 上で動作する **エンタープライズ AI エージェントプラットフォーム** の構築を目的とします。OpenMetadata を中核に据え、AI エージェントがビジネスデータのメタデータ管理・登録・検索を自動化します。

## ビジネス価値

| 課題 | 解決策 | 効果 |
|---|---|---|
| メタデータ登録の手動作業 | AI エージェントによる自動登録 | 工数 80% 削減 |
| データ資産の検索困難 | 自然言語検索 | 検索時間 90% 削減 |
| データ品質の一貫性欠如 | 自動バリデーション | 品質問題 70% 削減 |
| スキーマ変更の追跡漏れ | 自動スキーマ同期 | トレーサビリティ 100% |

## アーキテクチャの柱

1. **Tool-First** — すべての操作は Tool として定義し、エージェントから呼び出す
2. **Metadata-First** — OpenMetadata をデータ資産の単一情報源とする
3. **API-First** — Quarkus による標準化された REST API
4. **GitOps** — ArgoCD + Tekton による宣言的デプロイ
5. **Security-by-Design** — Keycloak による認証・認可

## フェーズ計画

```
Phase 1 (Month 1-2): 基盤構築
  - OpenShift AI 環境セットアップ
  - Quarkus Business API 実装
  - OpenMetadata 接続

Phase 2 (Month 3-4): エージェント実装
  - Schema Agent / Registration Agent
  - Search Agent / Validation Agent
  - Chat UI

Phase 3 (Month 5-6): 運用自動化
  - Operations Agent / Governance Agent
  - Tekton CI/CD パイプライン
  - 監視・アラート
```
