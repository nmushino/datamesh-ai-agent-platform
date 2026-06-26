# Technology Stack

## 技術選定一覧

### AI / ML レイヤー

| 技術 | バージョン | 用途 | 選定理由 |
|---|---|---|---|
| OpenShift AI (RHOAI) | 2.x | AI 基盤プラットフォーム | Red Hat サポート付きエンタープライズ ML PaaS |
| vLLM | 0.4.x | LLM 推論エンジン | OpenAI 互換 API、高スループット |
| IBM Granite | 20B Code Instruct | コード生成・分析 | 日本語対応、オンプレ動作可能 |
| LangGraph | 0.1.x | エージェントオーケストレーション | ステートフル、Human-in-the-Loop 対応 |
| LangChain | 0.2.x | ツール統合基盤 | 豊富なインテグレーション |

### バックエンドレイヤー

| 技術 | バージョン | 用途 | 選定理由 |
|---|---|---|---|
| Quarkus | 3.x | Business API | ネイティブコンパイル、Kubernetes ネイティブ |
| Python | 3.11+ | AI エージェント | LangGraph/LangChain エコシステム |
| FastAPI | 0.110.x | エージェント REST API | 非同期対応、OpenAPI 自動生成 |

### データ / メッセージング

| 技術 | バージョン | 用途 | 選定理由 |
|---|---|---|---|
| OpenMetadata | 1.3.x | データカタログ | オープンソース、豊富な API |
| PostgreSQL | 15.x | ビジネスデータ・チェックポイント | ACID 保証、LangGraph チェックポイント対応 |
| Apache Kafka | 3.x | イベントストリーミング | 高信頼性、AMQ Streams (Red Hat) |

### セキュリティ / 認証

| 技術 | バージョン | 用途 | 選定理由 |
|---|---|---|---|
| Keycloak | 24.x | IdP / OIDC | OpenShift 統合、SSO |
| Red Hat SSO | - | エンタープライズ Keycloak | サポート付き |

### デプロイ / 運用

| 技術 | バージョン | 用途 | 選定理由 |
|---|---|---|---|
| OpenShift | 4.14+ | コンテナプラットフォーム | エンタープライズ Kubernetes |
| ArgoCD | 2.x | GitOps | OpenShift GitOps オペレーター |
| Tekton | 1.x | CI/CD パイプライン | OpenShift Pipelines オペレーター |
| Helm | 3.x | パッケージ管理 | - |
| Kustomize | - | 環境差分管理 | Helm と組み合わせ使用 |

### フロントエンド

| 技術 | バージョン | 用途 | 選定理由 |
|---|---|---|---|
| React | 18.x | Chat UI | - |
| PatternFly | 5.x | UI コンポーネント | Red Hat Design System |
| RHDH (Backstage) | 1.x | 開発者ポータル | プラグイン統合 |

## バージョン互換性マトリクス

| OpenShift | RHOAI | vLLM | LangGraph | Quarkus |
|---|---|---|---|---|
| 4.14 | 2.5 | 0.4.2 | 0.1.x | 3.8.x |
| 4.15 | 2.6 | 0.4.2 | 0.1.x | 3.10.x |
