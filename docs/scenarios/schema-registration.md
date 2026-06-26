# シナリオ: スキーマ自動登録

## 概要

開発者が PostgreSQL のスキーマを変更した際に、AI エージェントが自動的に OpenMetadata に登録・更新するシナリオです。

## トリガー

1. **CI/CD トリガー**: Tekton パイプラインがスキーマ変更を検出
2. **手動トリガー**: Chat UI から「スキーマを同期して」と指示
3. **スケジュールトリガー**: 毎日 AM 2:00 に全スキーマを確認

## フロー詳細

```
1. スキーマ変更検出
   ├── Tekton が Flyway マイグレーションファイルの変更を検出
   └── Schema Agent を起動（引数: service_name, database_name）

2. 現状スキーマ取得 (Schema Agent)
   ├── OpenMetadata Tool: get_database_schema("postgresql-prod", "dronedb", "public")
   └── 現在登録されているテーブル・カラム情報を取得

3. 実際のスキーマ取得 (Schema Agent)
   ├── Business Tool: get_actual_schema("postgresql-prod", "dronedb")
   └── PostgreSQL の information_schema から実テーブル情報を取得

4. 差分計算 (Schema Agent)
   ├── 新規テーブルの特定
   ├── 削除テーブルの特定
   ├── カラム変更の特定
   └── 変更なし → 処理終了

5. 登録・更新 (Schema Agent)
   ├── 新規テーブル: OpenMetadata Tool: register_table_metadata()
   ├── カラム変更: OpenMetadata Tool: update_column_metadata()
   └── 削除テーブル: 要承認 → Human-in-the-Loop フロー

6. メタデータ自動生成 (Schema Agent)
   ├── LLM がテーブル名・カラム名からdescription を自動生成
   ├── PII カラム（email, phone, name 等）に自動タグ付け
   └── 推奨データ品質ルールを提案

7. 通知 (Kafka → Notification Service)
   ├── 変更サマリーを Kafka に発行
   └── 関係者に Slack 通知
```

## 入力例

```json
{
  "trigger": "tekton-pipeline",
  "service_name": "postgresql-prod",
  "database_name": "dronedb",
  "schema_name": "public",
  "migration_file": "V20240101__add_customer_preferences.sql"
}
```

## 出力例

```json
{
  "status": "success",
  "changes": {
    "new_tables": ["customer_preferences"],
    "modified_tables": ["customers"],
    "deleted_tables": []
  },
  "registered": [
    {
      "fqn": "postgresql-prod.dronedb.public.customer_preferences",
      "description": "顧客の設定情報を管理するテーブル",
      "tags": ["Customer", "Preferences"],
      "columns": 8
    }
  ],
  "quality_rules_suggested": [
    {
      "table": "customer_preferences",
      "column": "customer_id",
      "rule": "columnNotNull"
    }
  ]
}
```

## エラーケース

| ケース | 対応 |
|---|---|
| OpenMetadata 接続不可 | リトライ 3 回後に Kafka でアラート |
| テーブル削除検出 | Human-in-the-Loop で承認を取得 |
| LLM 生成失敗 | description を空で登録し、後で手動入力 |
