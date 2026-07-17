# Datamesh AI Agent Platform

OpenShift AI 上で動作する、OpenMetadata を中心としたエンタープライズ AI エージェントプラットフォームである。

## アーキテクチャ概要

```
            OpenShift AI
          (Qwen3 / Llama)
                 │
          AI Agent (LangGraph)
                 │
  ┌──────────────┴──────────────┐
  │                             │
OpenMetadata Tool         Business Tool
  │                             │
REST API                   REST API
  │                             │
OpenMetadata             Quarkus API
                               │
              ┌────────────────┼──────────────┐
              │                │              │
          PostgreSQL         Kafka        他システム
```

## ガードレールアーキテクチャ
```

                User
                  │
                  ▼
        API Gateway / MCP Gateway
                  │
        +----------------------+
        | Input Guardrail      |
        +----------------------+
                  │
                  ▼
          Planner Agent
                  │
                  ▼
          Policy Engine
        (OPA + Keycloak)
                  │
      ┌───────────┴────────────┐
      ▼                        ▼
 MCP Tool                REST Tool
 Camel Tool             SQL Tool
 Git Tool               Shell Tool
      │                        │
      └───────────┬────────────┘
                  ▼
        Output Guardrail
                  │
          Human Approval
                  │
             Audit Log

```
## ガードレール構成案
```
datamesh-ai-agent-platform

├── planner-agent
├── memory
├── mcp-client
├── mcp-server
├── tool-wrapper
├── ai-policy-gateway   ← 新規
│      ├── input filter
│      ├── OPA client
│      ├── tool policy
│      ├── output filter
│      ├── audit
│      └── cost limiter
├── opa
├── keycloak
├── opentelemetry
└── approval-service
```

## MCP Gateway (Red Hat Connectivity Link)

上図の「API Gateway / MCP Gateway」は **Red Hat Connectivity Link (rhcl-operator)** で実装する。

- **単位**: MCP サーバーはクラスタ(サイト)ごとに論理的にまとまった単位とする。サイトごとに `Gateway` を 1 つ、その配下に `mcp-server` への `HTTPRoute` を 1 本配置する。
- **Gateway API 実行基盤**: OpenShift 4.21 はネイティブに Gateway API をサポートしており(`GatewayClass.controllerName: openshift.io/gateway-controller/v1`)、Istio/OSSM の個別インストールは不要。
- **認証**: `AuthPolicy` で Keycloak (realm: `drone-platform`) に完全に委任する。`issuerUrl` を指定するだけで Authorino が JWKS を自動解決しトークン署名検証を行うため、Gateway 側に認証ロジックを自前実装しない。検証済み claim (`sub` / `preferred_username`) は下流ヘッダーに引き渡す。
- **認可**: Gateway 層では行わず、Planner Agent 後段の **OPA Policy Engine** の責務のまま残す(Tool policy はコード側)。
- **コスト制御**: `RateLimitPolicy` でユーザー単位に呼び出し回数の下限の歯止めをかける。トークン課金など詳細なコスト計算は `ai-policy-gateway` の cost limiter が担う。
- **Audit Log**: Gateway (Envoy) のアクセスログを OpenTelemetry Collector 経由で Audit Log に統合する。

導入コマンド:

```bash
# Operator インストール (setup に組み込み済み、Skupper と同じ流儀でサイトごとに実行)
./script/ocpdeploy.sh setup

# Gateway / HTTPRoute / AuthPolicy / RateLimitPolicy のデプロイ
./script/ocpdeploy.sh mcpgateway deploy
./script/ocpdeploy.sh mcpgateway status
./script/ocpdeploy.sh mcpgateway cleanup
```

マニフェスト一式は `quarkusdroneshop-ansible/openshift/` 配下:

```
connectivitylink-operator.yaml    # rhcl-operator Subscription
mcp-gateway.yaml                  # GatewayClass + Gateway
mcp-httproute.yaml                # mcp-server への HTTPRoute
mcp-gateway-authpolicy.yaml       # Keycloak OIDC AuthPolicy
mcp-gateway-ratelimitpolicy.yaml  # ユーザー単位 RateLimitPolicy
```

### 未着手・持ち越し事項

- `mcp-server` 実体 (Deployment/Service) の実装
- `Gateway` の TLS 用 Secret (`mcp-gateway-tls`) の用意
- 実クラスタでの `mcpgateway deploy` 動作検証
- `ai-policy-gateway` (input/output filter, OPA 連携) 側の実装

## 主要ユースケース

| ユースケース | 説明 |
|---|---|
| スキーマ自動登録 | DB スキーマ・API スペックを OpenMetadata に自動登録 |
| メタデータ検索 | 自然言語で OpenMetadata のアセットを検索・取得 |
| ビジネスデータ登録 | 顧客・BOM 等のビジネスデータをメタデータと紐付けて登録 |
| データ品質管理 | データ品質ルールの自動設定・検証 |

## 技術スタック

| レイヤー | 技術 |
|---|---|
| AI 基盤 | OpenShift AI, vLLM, IBM Granite |
| エージェント | LangGraph (Python) |
| バックエンド | Quarkus (Java) |
| メタデータ | OpenMetadata |
| メッセージング | Apache Kafka |
| データベース | PostgreSQL |
| ID 管理 | Keycloak |
| デプロイ | OpenShift, ArgoCD, Tekton |

## ドキュメント

- [book/](book/) — 詳細設計ドキュメント (全17章)
- [docs/architecture/](docs/architecture/) — アーキテクチャ設計
- [docs/implementation/](docs/implementation/) — 実装ガイド
- [docs/deployment/](docs/deployment/) — デプロイ手順
- [docs/adr/](docs/adr/) — アーキテクチャ決定記録

## クイックスタート

```bash
# 開発環境起動
./scripts/dev.sh

# chat-ui のみローカルで起動 (画面開発用、Keycloak認証は自動でスキップ)
./scripts/chat-ui.sh

# デプロイ
./scripts/deploy.sh
```

## Bug List

LangGraphの入れ子実行(グラフの中でさらに別のコンパイル済みグラフを呼び出す)自体にバグがあるため、stream()/.invoke()どちらでも、外側グラフ経由でノード関数を実行すると必ず失敗する。代わりにそのままPython関数として直接呼んだ場合は毎回成功する。これはcreate_react_agentが内部でコンパイル済みグラフを作る仕組みのため、サブエージェントをLangGraphの外側グラフの中で使う限り避けられないことがわかっている。対策として、サブエージェントのツール呼び出しループをLangGraphのネストしたグラフを使わず、LLM+ツールバインディングによる手動ループに置き換えることで回避する。

---

# Datamesh AI Agent Platform

An enterprise AI agent platform centered on OpenMetadata, running on OpenShift AI.

## Architecture Overview

```
            OpenShift AI
          (Qwen3 / Llama)
                 │
          AI Agent (LangGraph)
                 │
  ┌──────────────┴──────────────┐
  │                             │
OpenMetadata Tool         Business Tool
  │                             │
REST API                   REST API
  │                             │
OpenMetadata             Quarkus API
                               │
              ┌────────────────┼──────────────┐
              │                │              │
          PostgreSQL         Kafka        Other Systems
```

## Key Use Cases

| Use Case | Description |
|---|---|
| Automatic schema registration | Automatically register DB schemas and API specs into OpenMetadata |
| Metadata search | Search and retrieve OpenMetadata assets using natural language |
| Business data registration | Register business data (customers, BOM, etc.) linked to metadata |
| Data quality management | Automatically configure and validate data quality rules |

## Technology Stack

| Layer | Technology |
|---|---|
| AI Platform | OpenShift AI, vLLM, IBM Granite |
| Agent | LangGraph (Python) |
| Backend | Quarkus (Java) |
| Metadata | OpenMetadata |
| Messaging | Apache Kafka |
| Database | PostgreSQL |
| Identity Management | Keycloak |
| Deployment | OpenShift, ArgoCD, Tekton |

## Documentation

- [book/](book/) — Detailed design documentation (17 chapters)
- [docs/architecture/](docs/architecture/) — Architecture design
- [docs/implementation/](docs/implementation/) — Implementation guide
- [docs/deployment/](docs/deployment/) — Deployment instructions
- [docs/adr/](docs/adr/) — Architecture decision records

## Quick Start

```bash
# Start the development environment
./scripts/dev.sh

# Run chat-ui locally only (for UI development, Keycloak auth is skipped automatically)
./scripts/chat-ui.sh

# Deploy
./scripts/deploy.sh
```

