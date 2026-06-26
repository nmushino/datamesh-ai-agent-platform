# Appendix: Glossary (用語集)

| 用語 | 説明 |
|---|---|
| AI Agent | LangGraph で実装された自律的なタスク実行エンジン |
| Tool | AI Agent から呼び出される関数。@tool デコレータで定義 |
| Orchestrator | ユーザーの意図を解釈し、適切な Agent に委譲する調整役 |
| LangGraph | エージェントのワークフローをグラフで定義する Python フレームワーク |
| OpenMetadata | オープンソースのデータカタログ・メタデータ管理ツール |
| FQN | Fully Qualified Name。OpenMetadata でのエンティティ識別子 (例: `postgresql-prod.dronedb.public.customers`) |
| Quarkus | Java/Kotlin 向けクラウドネイティブフレームワーク。ネイティブコンパイル対応 |
| Human-in-the-Loop | 重要な操作の前に人間の承認を求める仕組み。LangGraph の `interrupt()` で実装 |
| Checkpoint | LangGraph が会話状態を PostgreSQL に保存する仕組み。会話の再開が可能 |
| AMQ Streams | Red Hat の Apache Kafka ディストリビューション |
| RHOAI | Red Hat OpenShift AI。OpenShift 上の ML プラットフォーム |
| vLLM | 高スループット LLM 推論エンジン。OpenAI API 互換エンドポイントを提供 |
| Granite | IBM の AI モデルシリーズ。コード生成に特化した Granite Code シリーズを使用 |
| GitOps | Git を唯一の信頼源として、宣言的にインフラ・アプリを管理する手法 |
| ArgoCD | Kubernetes 向け GitOps ツール。Git の状態を自動的にクラスターに同期 |
| Tekton | Kubernetes ネイティブな CI/CD パイプラインフレームワーク |
| Keycloak | オープンソースの IdP (Identity Provider)。OIDC/OAuth2 対応 |
| NetworkPolicy | Pod 間の通信を制御する Kubernetes リソース |
| HPA | Horizontal Pod Autoscaler。CPU/メモリ使用率に基づいて Pod 数を自動調整 |
| Intent | ユーザーの発話から解釈された操作の意図 (例: "metadata_search", "data_register") |
| Tool-First | 操作を Tool として抽象化し、エージェントから呼び出す設計原則 (ADR-0001) |
| Metadata-First | OpenMetadata をデータ資産の Single Source of Truth とする設計原則 (ADR-0002) |
| Single Source of Truth (SoT) | システム内で特定データの信頼できる唯一の情報源 |
| PII | Personally Identifiable Information。個人を特定できる情報 (氏名、メール、電話番号など) |
| Data Lineage | データの流れ・変換の追跡記録 (上流・下流のデータフロー) |
| CloudEvents | イベントデータのフォーマットを定義するオープン仕様 |
| OpenTelemetry | 分散トレーシング・メトリクス・ログを標準化するオープン仕様 |
