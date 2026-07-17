# kafka-topic-request

Developer Hub (RHDH) のカタログエンティティページに「Kafka トピック作成依頼」
タブを追加する Backstage フロントエンドプラグイン。

トピック名・対象サイト・追加コメントを入力して送信すると、AI Agent
Platform (`agent/orchestrator`) の `/api/v1/chat` にリクエストを送る。
AI Agent 側 (`agent/schema_agent`) は次の順で処理する:

1. `topic_exists` で対象サイトの実ブローカーに同名トピックが既にあるか確認
2. 既にあれば何もせず終了、無ければ追加コメント + 対象リポジトリの
   ソースコード/README (`get_github_readme` 等) から説明文を組み立てる
3. ユーザーに承認を求める(このプラグインでは「承認してトピックを作成する」
   ボタン)
4. 承認後、`create_kafka_topic` でブローカーにトピックを作成し、
   `register_topic_metadata` で OpenMetadata に登録する

## セットアップ

RHDH の `app-config.yaml` に AI Agent Platform の接続先を追加する:

```yaml
aiAgent:
  baseUrl: https://<orchestrator-route>
```

`packages/app` の `EntityPage.tsx` にタブとして追加する例:

```tsx
import { KafkaTopicRequestContent } from '@internal/plugin-kafka-topic-request';

// serviceEntityPage 等の該当箇所に追加
<EntityLayout.Route path="/kafka-topic" title="Kafka トピック作成依頼">
  <KafkaTopicRequestContent />
</EntityLayout.Route>
```

対象リポジトリは、カタログエンティティの `github.com/project-slug`
アノテーション (通常は `catalog-info.yaml` に記載) から自動取得される。
