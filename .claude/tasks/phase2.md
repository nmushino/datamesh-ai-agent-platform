# Phase 2: エージェント実装 (Month 3-4)

## 目標
主要 AI エージェントと Tool の実装、Chat UI の基本実装。

## タスク

### Tool 実装
- [ ] OpenMetadata Tool 群 (tools/openmetadata/)
  - [ ] get_database_schema
  - [ ] search_data_assets
  - [ ] register_table_metadata
  - [ ] get_data_lineage
  - [ ] create_quality_rule
- [ ] Business Tool 群 (tools/business/)
  - [ ] register_customer
  - [ ] search_customers
  - [ ] register_bom
  - [ ] search_inventory

### エージェント実装
- [ ] Orchestrator (agent/orchestrator/)
  - [ ] Intent classifier
  - [ ] Agent routing
  - [ ] LangGraph StateGraph 定義
  - [ ] PostgreSQL チェックポイント設定
- [ ] Schema Agent (agent/schema-agent/)
  - [ ] スキーマ取得・差分計算
  - [ ] 自動 description 生成
  - [ ] PII タグ自動付与
- [ ] Search Agent (agent/search-agent/)
  - [ ] 自然言語 → 検索クエリ変換
  - [ ] 並列検索
  - [ ] 結果整形
- [ ] Registration Agent (agent/registration-agent/)
  - [ ] 顧客登録フロー
  - [ ] BOM 登録フロー
  - [ ] Human-in-the-Loop 承認フロー

### プロンプト管理
- [ ] orchestrator system prompt (prompts/system/)
- [ ] schema agent prompt (prompts/schema/)
- [ ] search agent prompt (prompts/search/)

### Chat UI
- [ ] React + PatternFly プロジェクト初期化
- [ ] WebSocket 接続
- [ ] チャット UI コンポーネント
- [ ] OpenShift デプロイ

## 完了基準

- [ ] Chat UI から「スキーマを同期して」で Schema Agent が動作する
- [ ] 「顧客テーブルの説明は？」で Search Agent が回答する
- [ ] 顧客登録で Human-in-the-Loop 承認フローが動作する
- [ ] すべての Tool の単体テストが通る
