# Datamesh AI Agent Platform — Claude Code 作業指示

> このファイルは `.claude/` の優先命令です。セッション開始時に必ず読むこと。

## 1. 必須読み込みドキュメント

作業開始前に以下を必ず読むこと:

```
docs/architecture/logical-architecture.md   # アーキテクチャ全体像
book/chapter02-ai-native-architecture-principles.md  # 10の設計原則
book/chapter06-tool-framework.md            # Tool 設計ルール
book/appendix/coding-rules.md              # コーディング規約
```

## 2. 絶対禁止事項

| 禁止 | 理由 |
|------|------|
| AI から PostgreSQL へ直接接続 | Business API 経由が必須。DB は Business API だけが知っている |
| AI Agent 内にビジネスロジックを実装 | Business API に置くこと |
| プロンプト内にビジネスロジックを書く | ツール定義で表現すること |
| データベース認証情報を環境変数以外で管理 | Secret 経由のみ |
| ハードコードされた URL / 認証情報 | .env / Secret 経由のみ |

## 3. アーキテクチャ制約

```
[User] → [AI Agent (FastAPI/LangGraph)]
              │
    ┌─────────┴──────────┐
    │ OpenMetadata Tool  │ Business Tool  │ OpenShift Tool │ Git Tool │ Filesystem Tool │
    │        ↓           │       ↓        │                │          │                 │
    │  OpenMetadata API  │  Business API  │  oc/kubectl    │   git    │   local files   │
    │                    │  (Quarkus)     │                │          │                 │
    │                    │       ↓        │                │          │                 │
    │                    │  PostgreSQL    │                │          │                 │
    │                    │  Kafka         │                │          │                 │
    └────────────────────┴────────────────┴────────────────┴──────────┴─────────────────┘
```

**AI は推論のみ。外部システムへのアクセスは全て Tool 経由。**

## 4. ツール実装ルール

```python
# ✅ 正しい: Tool はエラーを dict で返す
@tool
def my_tool(param: str) -> dict:
    try:
        result = do_something(param)
        return {"result": result, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}  # 例外を LLM に渡さない

# ❌ 禁止: Tool から例外を raise する
@tool
def bad_tool(param: str) -> dict:
    result = do_something(param)  # これが raise したら LLM が壊れる
    return result
```

## 5. ディレクトリルール

```
tools/          各ツールはここにモジュールとして追加
  openmetadata/ OpenMetadata Tool 群
  business/     Business Tool 群 (Quarkus API 呼び出し)
  openshift/    OpenShift Tool 群 (oc/kubectl)
  git/          Git Tool 群
  filesystem/   Filesystem Tool 群

agent/          LangGraph エージェント実装
  orchestrator/ ルーター・グラフ定義・FastAPI
  *-agent/      各専門エージェント (create_react_agent)

backend/        Quarkus Business API (Java)
  business-api/ REST API・DB・Kafka

deployment/     全デプロイメントマニフェスト
  helm/         Helm Chart
  kustomize/    Kustomize base + overlays
  tekton/       CI/CD パイプライン
  argocd/       GitOps
  openshift/    OpenShift 固有リソース
  monitoring/   Prometheus / Grafana

prompts/        LLM プロンプトファイル (Markdown)
tests/          テストコード (unit / integration)
```

## 6. 新しい Tool を追加する手順

1. `tools/<カテゴリ>/<tool_name>.py` に `@tool` 関数を実装
2. `tools/requirements.txt` に依存ライブラリを追記
3. 対象エージェントの `agent/<name>-agent/agent.py` の `tools` リストに追加
4. `tests/integration/test_<tool_name>.py` に統合テストを追加
5. `book/chapter06-tool-framework.md` に Tool の説明を追記

## 7. ワークフロー実装ルール

- **必ず LangGraph の StateGraph / create_react_agent を使う**
- 承認が必要な操作は `NodeInterrupt` で Human-in-the-Loop を挟む
- エージェント間通信は `AgentState` の `active_agent` フィールドで制御
- PostgreSQL チェックポイント (`PostgresSaver`) を使い会話履歴を永続化

## 8. テストルール

```bash
# 実行方法
cd datamesh-ai-agent-platform
pytest tests/ -v --cov=tools --cov=agent --cov-report=term-missing

# カバレッジ最低ライン: 70%
```

- Tool の統合テストは必ず実際の API サーバー (またはモック) に対して実行
- `pytest.mark.integration` でタグ付けして CI で分離可能にする

## 9. コミットメッセージ規約

```
feat(tool): OpenShift get_pods ツール追加
fix(agent): registration-agent の承認フロー修正
docs(chapter): observability chapter 追加
test(integration): git_tools 統合テスト追加
```

## 10. 10の設計原則 (要約)

1. **AI Performs Reasoning** — AI は推論のみ、実行は Tool
2. **Tool First** — 全外部操作は Tool 経由
3. **Metadata First** — OpenMetadata が Single Source of Truth
4. **API First** — 全操作は REST API 経由
5. **Stateless Agents** — エージェントは状態を持たない (DB に外部化)
6. **Workflow Before Prompt** — ワークフローは LangGraph で定義、プロンプトに書かない
7. **Cloud Native** — OpenShift / コンテナ / GitOps
8. **Security by Default** — Keycloak OIDC / NetworkPolicy / Secret
9. **Observable by Default** — OpenTelemetry / Prometheus / Grafana / Jaeger
10. **Model Agnostic** — LLM を差し替え可能な設計 (vLLM OpenAI互換 API)
