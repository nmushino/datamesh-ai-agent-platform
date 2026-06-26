# ADR-0002: Metadata-First アーキテクチャの採用

## ステータス

採用済み (2024-01-01)

## コンテキスト

ビジネスデータとメタデータの管理をどのように統合するかを決定する必要がある。
特に、ビジネス API がデータを登録する際に OpenMetadata との連携をどのタイミングで行うかが問題となる。

## 決定

**すべてのビジネスエンティティは OpenMetadata に登録・管理する (Metadata-First)**

データを登録する際は、ビジネスデータ（PostgreSQL）と同時にメタデータ（OpenMetadata）も更新する。
OpenMetadata をデータ資産の Single Source of Truth とする。

## アーキテクチャ

```
データ登録フロー:
  1. Quarkus API が PostgreSQL に INSERT
  2. Quarkus API が OpenMetadata のメタデータを同期 (非同期 / Kafka 経由)
  3. AI エージェントは OpenMetadata を検索してデータを発見する
```

## 理由

1. **データ発見性**: AI エージェントが OpenMetadata を検索すれば全データを発見できる
2. **ガバナンス**: データの所有者・分類・品質を一元管理できる
3. **リネージ**: データの流れを自動的に追跡できる
4. **スキーマ進化対応**: スキーマ変更が自動的に OpenMetadata に反映される

## 結果

- Quarkus API は登録・更新後に `MetadataSyncService` を呼び出す
- 同期失敗はビジネス処理を止めない（best-effort sync）
- 重要な同期失敗は Kafka 経由でアラートを発行する
- AI エージェントは直接 PostgreSQL を参照しない（OpenMetadata → Quarkus API の順でアクセス）

## トレードオフ

| 利点 | 欠点 |
|---|---|
| データ発見性が高い | OpenMetadata 障害時の対応が必要 |
| 一元管理 | 同期遅延が発生する可能性 |
| AI フレンドリー | 初期セットアップコストが高い |
