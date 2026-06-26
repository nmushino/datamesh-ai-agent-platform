# Phase 1: 基盤構築 (Month 1-2)

## 目標
OpenShift AI 環境のセットアップと Quarkus Business API の基本実装。

## タスク

### インフラセットアップ
- [ ] OpenShift 4.14 クラスター準備
- [ ] RHOAI オペレーター インストール
- [ ] AMQ Streams (Kafka) オペレーター インストール
- [ ] OpenMetadata デプロイ (deployment/openshift/openmetadata.yaml)
- [ ] PostgreSQL デプロイ
- [ ] Keycloak デプロイ・設定

### vLLM / Granite セットアップ
- [ ] Granite モデルダウンロード・PVC 配置
- [ ] vLLM ServingRuntime 作成
- [ ] InferenceService デプロイ
- [ ] API エンドポイント疎通確認

### Quarkus Business API
- [ ] プロジェクト初期化 (`quarkus create app`)
- [ ] CustomerResource 実装
- [ ] CustomerService / CustomerRepository 実装
- [ ] PostgreSQL 接続設定
- [ ] Kafka Producer 実装
- [ ] Keycloak OIDC 設定
- [ ] OpenShift デプロイ
- [ ] Tekton パイプライン作成

### OpenMetadata 接続
- [ ] OpenMetadata Python クライアントラッパー実装
- [ ] PostgreSQL サービス登録 (OpenMetadata)
- [ ] Kafka サービス登録 (OpenMetadata)
- [ ] 疎通確認

## 完了基準

- [ ] vLLM から Granite モデルに API リクエストが通る
- [ ] Quarkus API で顧客の CRUD ができる
- [ ] OpenMetadata に customers テーブルが登録されている
- [ ] Kafka に顧客登録イベントが発行される
