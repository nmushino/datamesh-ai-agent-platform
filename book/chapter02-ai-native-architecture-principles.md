# Chapter 2: AI-Native Architecture Principles

## 概要

本章では、エンタープライズ AI エージェントプラットフォームを支える **10 のアーキテクチャ原則** を定義します。これらは単なる設計指針ではなく、すべての実装判断の基準となる不変の原則です。

| # | 原則 | 一言要約 |
|---|------|---------|
| 1 | AI Performs Reasoning | AI は推論のみ — 実行は Tool が担う |
| 2 | Tool First | 全外部操作は Tool 経由 |
| 3 | Metadata First | OpenMetadata が Single Source of Truth |
| 4 | API First | 全操作は REST API 経由 |
| 5 | Stateless Agents | 状態は外部 DB に永続化 |
| 6 | Workflow Before Prompt | ワークフローは LangGraph で定義 — プロンプトに書かない |
| 7 | Cloud Native | OpenShift / コンテナ / GitOps |
| 8 | Security by Default | Keycloak OIDC / NetworkPolicy / Secret |
| 9 | Observable by Default | OpenTelemetry / Prometheus / Grafana / Jaeger |
| 10 | Model Agnostic | LLM を差し替え可能な設計 |

---

## 原則 1: Cloud-Native Design

### 定義
コンテナ・Kubernetes を前提とした設計を行い、スケーラビリティ・自己修復・ゼロダウンタイムデプロイを標準とする。

### 実践
```yaml
# すべてのコンポーネントは Kubernetes Deployment として動作する
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-agent-orchestrator
spec:
  replicas: 2                    # 冗長性
  strategy:
    type: RollingUpdate          # ゼロダウンタイム
  template:
    spec:
      containers:
      - name: orchestrator
        livenessProbe:           # 自己修復
          httpGet:
            path: /health
        readinessProbe:          # トラフィック制御
          httpGet:
            path: /health/ready
```

### チェックリスト
- [ ] すべてのコンポーネントはステートレスに設計する（状態は PostgreSQL/Kafka に委譲）
- [ ] ヘルスチェックエンドポイント `/health`, `/health/ready` を必ず実装する
- [ ] 環境依存の設定は ConfigMap / Secret で外部化する
- [ ] リソースの request/limit を必ず設定する

---

## 原則 2: AI-Native Approaches

### 定義
AI は後付けの機能ではなく、**システムの中核** として設計する。すべてのユーザーインターフェースは AI 対話を主要インターフェースとして設計する。

### 従来型 vs AI-Native

```
【従来型】
ユーザー → UI フォーム入力 → API → DB
         （固定フロー、人間が操作を知る必要あり）

【AI-Native】
ユーザー → 自然言語 → AI Agent → Tool → API → DB
         （柔軟なフロー、AIが操作を判断）
```

### 実践
```python
# AI が意図を解釈し、適切な Tool を選択する
user_input = "先月の顧客登録数と、最も登録が多かった日を教えて"

# AI Agent が自律的に以下を実行:
# 1. search_customers(date_range="last_month") を呼び出す
# 2. 結果を集計する
# 3. 自然言語で回答を生成する
```

### チェックリスト
- [ ] すべての主要操作は自然言語からトリガーできる
- [ ] AI が操作を実行した際はログに記録し、追跡可能にする
- [ ] フォールバック UI（フォーム入力）も用意する（AI 障害時）

---

## 原則 3: Agent-First Methodology

### 定義
複雑なタスクは **専門化されたエージェント** に分割して委譲する。単一の汎用エージェントではなく、ドメイン特化エージェントの協調で実現する。

### エージェント分割の基準

```
1 エージェント = 1 ドメイン

Schema Agent     → スキーマ管理のみ
Search Agent     → 検索のみ
Registration Agent → 登録・更新のみ
Operations Agent → 運用・監視のみ
```

### エージェント間委譲パターン

```python
# Orchestrator がルーティングを担う
def route_to_agent(state: AgentState) -> str:
    intent = state["intent"]
    routing = {
        "schema_sync":    "schema_agent",
        "metadata_search": "search_agent",
        "data_register":  "registration_agent",
        "ops_check":      "operations_agent",
    }
    return routing.get(intent, "search_agent")
```

### チェックリスト
- [ ] エージェントは自身のドメイン外の Tool を使用しない
- [ ] エージェント間の通信は LangGraph State を通じて行う
- [ ] 各エージェントは独立してテスト可能に設計する

---

## 原則 4: Tool-First Patterns

### 定義
エージェントの能力は **Tool の集合** で定義される。ビジネスロジックはエージェントに直接書かず、すべて Tool として実装する。

### Tool 設計の 4 原則

```python
# 1. 単一責務: 1 Tool = 1 操作
@tool
def get_table_schema(service: str, database: str, schema: str) -> dict:
    """テーブルスキーマを取得する（取得のみ、変更しない）"""
    ...

# 2. 冪等性: 同じ引数で何度呼んでも同じ結果
@tool
def register_table_metadata(fqn: str, description: str) -> dict:
    """メタデータを登録する（存在すれば更新、なければ作成）"""
    return client.create_or_update(fqn, description)  # upsert

# 3. 明確な型定義: LLM が正しく使えるよう引数・戻り値を明示
@tool
def search_data_assets(
    query: str,
    asset_type: Literal["table", "topic", "pipeline", "all"] = "all",
    limit: int = Field(default=10, ge=1, le=100)
) -> list[DataAsset]:
    ...

# 4. 安全なデフォルト: 破壊的操作は明示的に要求
@tool
def delete_table_metadata(
    fqn: str,
    confirm: bool = False  # デフォルトは実行しない
) -> dict:
    if not confirm:
        return {"error": "削除は confirm=True を明示的に指定してください"}
    ...
```

### チェックリスト
- [ ] すべての外部システム操作は `@tool` デコレータで定義する
- [ ] Tool の docstring には Args/Returns/Raises を必ず記述する
- [ ] Tool の単体テストを作成する
- [ ] Tool 呼び出しはすべて監査ログに記録する

---

## 原則 5: API-First Integration

### 定義
すべての統合は **REST API** を通じて行う。直接のライブラリ呼び出しや DB 直接アクセスは避け、API 契約を通じて疎結合を保つ。

### API 設計標準

```
OpenMetadata Tool  →  OpenMetadata REST API  →  OpenMetadata
Business Tool      →  Quarkus REST API       →  PostgreSQL / Kafka

※ Business Tool は Quarkus API を経由し、DB に直接アクセスしない
```

### API バージョニング戦略

```
/api/v1/customers     # 現行バージョン
/api/v2/customers     # 次期バージョン（並行稼働期間あり）
```

### チェックリスト
- [ ] すべての API は OpenAPI 3.0 仕様で定義する
- [ ] API は `/api/v{N}/` プレフィックスで versioning する
- [ ] 破壊的変更は新バージョンで提供し、旧バージョンを 3 ヶ月維持する
- [ ] API キーまたは JWT で認証を必須とする

---

## 原則 6: Metadata-First Management

### 定義
すべてのデータ資産は **OpenMetadata に登録** され、AI が検索・参照できる状態を常に維持する。OpenMetadata をデータ資産の Single Source of Truth とする。

### メタデータ管理の階層

```
OpenMetadata
├── データサービス
│   ├── postgresql-prod (DB サービス)
│   │   └── dronedb.public.customers (テーブル)
│   └── kafka-prod (メッセージングサービス)
│       └── drone-delivery-events (トピック)
├── ビジネスグロサリー
│   └── 顧客 → customers テーブルにリンク
└── データ品質
    └── customers.email: columnNotNull, columnValuesToMatchRegex
```

### 登録タイミング

| イベント | トリガー | 担当 |
|---|---|---|
| DB スキーマ変更 | Tekton パイプライン | Schema Agent |
| テーブル作成 | Flyway マイグレーション完了 | Schema Agent |
| ビジネスデータ登録 | Quarkus API の POST 後 | MetadataSyncService |
| Kafka トピック作成 | トピック作成イベント | Schema Agent |

### チェックリスト
- [ ] 新規テーブル作成時は必ず OpenMetadata に登録する
- [ ] PII データには必ずタグを付与する
- [ ] データオーナーを必ず設定する
- [ ] OpenMetadata 同期失敗時はアラートを発行する

---

## 原則 7: Open Standards Adherence

### 定義
ベンダーロックインを避け、**オープン標準** に準拠したコンポーネントを優先する。

### 採用するオープン標準

| 標準 | 用途 | 実装 |
|---|---|---|
| OpenAI API 互換 | LLM 推論 API | vLLM (OpenAI 互換エンドポイント) |
| OpenAPI 3.0 | REST API 仕様 | Quarkus SmallRye OpenAPI |
| CloudEvents | イベント形式 | Kafka + CloudEvents SDK |
| OpenTelemetry | 観測可能性 | Quarkus OpenTelemetry 拡張 |
| OIDC / OAuth2 | 認証・認可 | Keycloak |
| Helm / Kustomize | パッケージ管理 | Kubernetes 標準 |

### LLM 互換性の確保

```python
# vLLM は OpenAI API 互換のため、LangChain の ChatOpenAI をそのまま使用
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url=os.getenv("VLLM_BASE_URL"),  # http://vllm:8080/v1
    api_key="not-needed",                  # vLLM は API キー不要
    model="ibm-granite-20b-code-instruct", # または "meta-llama-3-8b-instruct"
)
# → vLLM を Granite に変えても、Llama に変えても、このコードは変わらない
```

### チェックリスト
- [ ] LLM は OpenAI API 互換インターフェースを通じて呼び出す
- [ ] イベントは CloudEvents 形式で発行する
- [ ] すべての API は OpenAPI 3.0 で文書化する
- [ ] 認証は OIDC 標準に準拠する

---

## 原則 8: GitOps Practices

### 定義
すべてのインフラ・アプリケーション設定は **Git リポジトリを唯一の真実** とし、ArgoCD が Git の状態を自動的にクラスターに同期する。

### GitOps フロー

```
開発者
  │── コードをコミット → Git (feature branch)
  │── PR 作成 → Tekton CI パイプライン実行
  │               ├── テスト
  │               ├── ビルド・イメージプッシュ
  │               └── kustomize の image タグ更新
  └── PR マージ → ArgoCD が自動同期 → OpenShift
```

### 環境ブランチ戦略

```
main        → dev 環境に自動デプロイ
release/*   → staging 環境に自動デプロイ
tags/v*.*.*  → prod 環境に手動承認後デプロイ
```

### チェックリスト
- [ ] 本番環境への手動 `oc apply` を禁止する
- [ ] すべての設定変更は PR 経由で行う
- [ ] Secret は External Secrets Operator で管理する
- [ ] ArgoCD の Self-Heal を有効にする

---

## 原則 9: Security-by-Design

### 定義
セキュリティは後から追加するものではなく、**設計の最初から組み込む**。最小権限の原則を徹底し、ゼロトラストネットワークを前提とする。

### セキュリティレイヤー

```
┌─────────────────────────────────────────────┐
│ 外部境界: Route + TLS 終端                   │
│   └── Keycloak JWT 検証                      │
├─────────────────────────────────────────────┤
│ サービス間: NetworkPolicy                    │
│   └── 必要なポートのみ許可                   │
├─────────────────────────────────────────────┤
│ Pod 内: 最小権限 ServiceAccount              │
│   └── Secret は環境変数でマウント            │
├─────────────────────────────────────────────┤
│ データ: 暗号化                               │
│   └── 保存時: PostgreSQL 暗号化              │
│   └── 転送時: TLS 必須                       │
└─────────────────────────────────────────────┘
```

### AI 固有のセキュリティ考慮

```python
# プロンプトインジェクション対策
def sanitize_user_input(user_input: str) -> str:
    """ユーザー入力をサニタイズしてインジェクションを防ぐ"""
    # システムプロンプトへの注入試みを検出
    dangerous_patterns = [
        "ignore previous instructions",
        "you are now",
        "system:",
    ]
    for pattern in dangerous_patterns:
        if pattern.lower() in user_input.lower():
            raise SecurityError(f"不正な入力が検出されました")
    return user_input

# Tool 実行の認可チェック
def check_tool_authorization(tool_name: str, user_roles: list[str]) -> bool:
    """Tool の実行権限を確認する"""
    tool_permissions = {
        "delete_table_metadata": ["admin", "data-steward"],
        "register_customer": ["operator", "admin"],
        "search_data_assets": ["viewer", "operator", "admin"],
    }
    required = tool_permissions.get(tool_name, ["admin"])
    return any(role in required for role in user_roles)
```

### チェックリスト
- [ ] すべての API エンドポイントは認証を必須とする
- [ ] ServiceAccount に ClusterAdmin を付与しない
- [ ] Secret を Git にコミットしない（External Secrets を使用）
- [ ] AI への入力はサニタイズする
- [ ] Tool 実行は RBAC でアクセス制御する
- [ ] 監査ログをすべての操作に記録する

---

---

## 原則 9 (補足): Observable by Default

### 定義
すべてのコンポーネントはデフォルトで観測可能である。ログ・メトリクス・トレースは後付けではなく設計から組み込む。

### 実践
- OpenTelemetry による分散トレース (AI Agent → Tool → Business API → DB)
- Prometheus メトリクス (LLM レイテンシ・Tool 成功率・トークンコスト)
- JSON 構造化ログ (trace_id / span_id / intent / user_id を必須フィールド化)
- Grafana ダッシュボード (`deployment/monitoring/grafana-dashboard.json`)

### チェックリスト
- [ ] 全コンポーネントに `OTEL_EXPORTER_OTLP_ENDPOINT` を設定する
- [ ] `trace_id` がログ・メトリクス・トレース間で共有されている
- [ ] Grafana ダッシュボードで LLM コストが可視化されている
- [ ] Prometheus アラートルールが設定されている

---

## 原則 10: Model Agnostic

### 定義
AI モデルは差し替え可能でなければならない。特定 LLM プロバイダーへの依存をアーキテクチャレベルで排除する。

### 背景
AI モデルの進化は急速であり、今日の最良モデルが1年後も最良とは限らない。IBM Granite から Meta Llama へ、または将来の新モデルへの切り替えがコード変更なしに行えることが、プラットフォームの長期的価値を保証する。

### 実践

```python
# agent/common/llm.py — モデル切り替えは環境変数のみ
from functools import lru_cache
from langchain_openai import ChatOpenAI
import os

@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    """vLLM OpenAI 互換 API 経由でモデルに接続。
    VLLM_MODEL_NAME を変えるだけでモデルを切り替えられる。
    """
    return ChatOpenAI(
        base_url=os.environ["VLLM_BASE_URL"],       # vLLM エンドポイント
        api_key=os.getenv("VLLM_API_KEY", "dummy"), # vLLM は認証不要の場合あり
        model=os.environ["VLLM_MODEL_NAME"],         # granite-20b / llama-3-70b 等
        temperature=0,
        max_tokens=4096,
    )
```

```yaml
# モデル切り替えは ConfigMap / InferenceService の変更のみ
# アプリコードに手を加えない
env:
  - name: VLLM_MODEL_NAME
    value: "ibm-granite/granite-20b-code-instruct-8k"
  # → 切り替え時はここだけ変える:
  # value: "meta-llama/Meta-Llama-3-70B-Instruct"
```

### モデル選定基準

| 基準 | 説明 |
|------|------|
| OpenAI 互換 API | `/v1/chat/completions` が必須 |
| Tool Calling 対応 | `tools` パラメータのサポート |
| vLLM 対応 | OpenShift AI の ServingRuntime で動作 |
| コンテキスト長 | 最低 8K トークン (Tool 応答含む) |

### チェックリスト
- [ ] LLM への接続は `get_llm()` のみを経由する
- [ ] モデル名がソースコードにハードコードされていない
- [ ] 異なるモデルで同じ統合テストが通ることを確認している
- [ ] モデル切り替え手順が `docs/` に記載されている

---

## 10 原則のまとめ

```
┌──────────────────────────────────────────────────────────────────┐
│                   10 の設計原則                                   │
│                                                                    │
│  1. AI Performs Reasoning  → AI は推論のみ、実行は Tool           │
│  2. Tool First             → 全外部操作は Tool 経由               │
│  3. Metadata First         → OpenMetadata = Single Source of Truth │
│  4. API First              → REST API による疎結合                │
│  5. Stateless Agents       → 状態は PostgreSQL に外部化            │
│  6. Workflow Before Prompt → LangGraph でワークフロー定義          │
│  7. Cloud Native           → OpenShift / コンテナ / GitOps        │
│  8. Security by Default    → Keycloak / NetworkPolicy / Secret    │
│  9. Observable by Default  → OpenTelemetry / Prometheus / Jaeger  │
│ 10. Model Agnostic         → vLLM OpenAI 互換 API で差し替え可能  │
└──────────────────────────────────────────────────────────────────┘
```

10 の原則は互いに強化し合います。**Tool First (2)** により各操作が独立してテスト可能になり、**Workflow Before Prompt (6)** によりビジネスフローがコードとして管理され、**Observable by Default (9)** により問題を早期検知でき、**Model Agnostic (10)** により AI の進化に継続的に追従できます。
