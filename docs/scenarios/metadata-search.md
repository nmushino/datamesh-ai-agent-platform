# シナリオ: 自然言語メタデータ検索

## 概要

ユーザーが Chat UI または RHDH プラグインから自然言語でデータ資産を検索するシナリオです。

## ユーザーストーリー

```
As a データアナリスト
I want to 自然言語で「顧客の注文履歴」と入力するだけで
So that 関連するテーブル・API・トピックを一覧で確認できる
```

## 対話例

```
User: 「ドローンの配送状況を確認できるテーブルはありますか？」

Agent: 「以下のデータ資産が見つかりました：

📊 テーブル
  1. postgresql-prod.dronedb.public.deliveries
     説明: ドローン配送の状態管理テーブル
     オーナー: drone-ops-team@company.com
     最終更新: 2024-01-15
     タグ: [Delivery, Operations]
     
  2. postgresql-prod.dronedb.public.drone_status
     説明: ドローンのリアルタイム状態テーブル
     オーナー: drone-dev-team@company.com

📨 Kafka トピック
  1. drone-delivery-events
     説明: ドローン配送イベントストリーム
     スキーマ: Avro (deliveries.avsc)

詳細を確認したいものはありますか？
また、データ品質スコアや lineage も確認できます。」

User: 「deliveries テーブルの lineage を教えて」

Agent: 「deliveries テーブルのデータリネージです：

上流 (データソース):
  ← orders テーブル (注文情報)
  ← drone_assignments テーブル (アサイン情報)

下流 (データ活用先):
  → delivery_analytics (BI ダッシュボード)
  → customer_notifications (通知サービス)
  → drone-delivery-events (Kafka トピック)」
```

## フロー詳細

```
1. ユーザー入力受信 (Chat UI → Orchestrator)
   └── WebSocket でリアルタイム通信

2. 意図分類 (Orchestrator)
   ├── intent: "metadata_search"
   └── Search Agent に委譲

3. クエリ変換 (Search Agent)
   ├── 自然言語 → OpenMetadata 検索クエリに変換
   └── 「ドローンの配送状況」→ "drone delivery status"

4. 並列検索 (Search Agent)
   ├── OpenMetadata Tool: search_data_assets(query, asset_type="table")
   ├── OpenMetadata Tool: search_data_assets(query, asset_type="topic")
   └── OpenMetadata Tool: search_data_assets(query, asset_type="pipeline")

5. 結果統合・整形 (Search Agent)
   ├── 結果をスコア順にソート
   ├── ビジネスコンテキストを付加
   └── Markdown 形式でレスポンス生成

6. フォローアップ対応 (Search Agent)
   ├── lineage リクエスト → get_data_lineage()
   ├── 品質スコアリクエスト → get_quality_metrics()
   └── サンプルデータリクエスト → 要承認
```

## RHDH プラグイン統合

```typescript
// frontend/developer-hub-plugin/src/components/MetadataSearch.tsx

export const MetadataSearchPanel = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);

  const handleSearch = async () => {
    const response = await fetch('/api/agent/search', {
      method: 'POST',
      body: JSON.stringify({ query, intent: 'metadata_search' }),
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await response.json();
    setResults(data.assets);
  };

  return (
    <Card>
      <CardHeader title="データ資産検索" />
      <CardContent>
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder="例: 顧客の注文履歴テーブル"
          onSearch={handleSearch}
        />
        <AssetList assets={results} />
      </CardContent>
    </Card>
  );
};
```
