# Appendix: Roadmap

## フェーズ計画

### Phase 1: 基盤構築 (Month 1-2)

**目標**: OpenShift AI 環境 + Quarkus API + OpenMetadata の疎通確認

```
Week 1-2: インフラセットアップ
  ✓ OpenShift 4.14 クラスター準備
  ✓ RHOAI / AMQ Streams / OpenMetadata デプロイ
  ✓ Keycloak 設定

Week 3-4: vLLM / Granite セットアップ
  ✓ Granite モデルダウンロード・PVC 配置
  ✓ vLLM InferenceService デプロイ
  ✓ OpenAI API 互換エンドポイント確認

Week 5-6: Quarkus Business API (顧客)
  ✓ CustomerResource / Service / Repository 実装
  ✓ Kafka イベント発行
  ✓ OpenMetadata 同期

Week 7-8: OpenMetadata 接続・検証
  ✓ Python クライアントラッパー実装
  ✓ customers テーブルのメタデータ登録確認
  ✓ Tekton パイプライン作成
```

**成功基準**:
- vLLM から Granite に API リクエストが通る
- Quarkus API で顧客 CRUD が動作する
- OpenMetadata に customers テーブルが登録されている

---

### Phase 2: エージェント実装 (Month 3-4)

**目標**: 主要 Tool / Agent 実装 + Chat UI 基本動作

```
Week 9-10: Tool 実装
  - OpenMetadata Tool 群 (get_schema, search, register, lineage, quality)
  - Business Tool 群 (register/search customer, bom, inventory)
  - 全 Tool の単体テスト

Week 11-12: エージェント実装
  - Orchestrator (Intent Classifier + Router)
  - Schema Agent
  - Search Agent
  - PostgreSQL チェックポイント設定

Week 13-14: Registration Agent + Human-in-the-Loop
  - Registration Agent 実装
  - Kafka 経由の承認リクエスト
  - 承認後の再開フロー

Week 15-16: Chat UI
  - React + PatternFly プロジェクト
  - WebSocket 接続
  - OpenShift デプロイ
```

**成功基準**:
- 「スキーマを同期して」で Schema Agent が動作する
- 「顧客テーブルの説明は？」で Search Agent が回答する
- 顧客登録で Human-in-the-Loop フローが動作する

---

### Phase 3: 運用自動化 (Month 5-6)

**目標**: Operations Agent + 本番 CI/CD + 監視

```
Week 17-18: 追加エージェント
  - Validation Agent (データ品質検証)
  - Operations Agent (OpenShift 監視・運用)
  - Governance Agent (承認フロー管理)

Week 19-20: RHDH Plugin
  - メタデータ検索パネル
  - Agent 操作パネル
  - Topology ビュー統合

Week 21-22: 本番 CI/CD
  - Tekton Pipeline 完成
  - ArgoCD App-of-Apps 設定
  - staging / prod 環境への自動デプロイ

Week 23-24: 監視・アラート
  - Prometheus メトリクス
  - Grafana ダッシュボード
  - アラートルール設定
  - 障害対応手順書作成
```

**成功基準**:
- 本番環境への手動デプロイが不要になっている
- Grafana でエージェントの健全性が可視化されている
- すべての主要ユースケースが E2E テストで検証されている

---

## バックログ (Phase 4 以降)

| 優先度 | 機能 | 概要 |
|---|---|---|
| High | CSV 一括インポート | CSV ファイルからビジネスデータを一括登録 |
| High | Workflow Agent | 複数エージェントを跨ぐ複雑なワークフロー管理 |
| Medium | Coding Agent | スキーマからの CRUD コード自動生成 |
| Medium | データ品質レポート | OpenMetadata の品質スコアのレポート自動生成 |
| Medium | Slack Bot 統合 | Slack から直接 Agent を操作 |
| Low | Multi-tenant 対応 | 複数チーム・プロジェクトの分離 |
| Low | モデルスイッチング | 会話中にモデルを切り替え (Granite ↔ Llama) |
