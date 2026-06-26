# Chapter 5: AI Agent Framework

## エージェント一覧

| エージェント | 役割 | 主要 Tool |
|---|---|---|
| Orchestrator | ルーティング・調整 | 全エージェント |
| Schema Agent | スキーマ取得・登録 | OpenMetadata Tool |
| Registration Agent | データ登録・更新 | Business Tool, OpenMetadata Tool |
| Validation Agent | データ品質検証 | Business Tool |
| Search Agent | メタデータ・データ検索 | OpenMetadata Tool, Business Tool |
| Planning Agent | タスク計画立案 | - |
| Workflow Agent | ワークフロー実行 | 全 Tool |
| Coding Agent | コード生成・レビュー | GitHub Tool, Filesystem Tool |
| Operations Agent | 運用・監視 | OpenShift Tool, Kubernetes Tool |
| Governance Agent | ガバナンス・承認 | OpenMetadata Tool |

## LangGraph による実装パターン

### Orchestrator グラフ定義

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    intent: str
    agent_output: dict
    requires_approval: bool

def create_orchestrator_graph():
    graph = StateGraph(AgentState)

    # ノード追加
    graph.add_node("intent_classifier", classify_intent)
    graph.add_node("schema_agent", schema_agent_node)
    graph.add_node("search_agent", search_agent_node)
    graph.add_node("registration_agent", registration_agent_node)
    graph.add_node("human_approval", human_approval_node)

    # エッジ定義
    graph.set_entry_point("intent_classifier")
    graph.add_conditional_edges(
        "intent_classifier",
        route_to_agent,
        {
            "schema": "schema_agent",
            "search": "search_agent",
            "register": "registration_agent",
        }
    )
    graph.add_conditional_edges(
        "registration_agent",
        check_approval_needed,
        {
            "approved": END,
            "needs_approval": "human_approval",
        }
    )

    return graph.compile()
```

### Schema Agent 実装

```python
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI  # vLLM 互換エンドポイント

@tool
def get_table_schema(table_name: str, database: str) -> dict:
    """OpenMetadata からテーブルスキーマを取得する"""
    client = OpenMetadataClient()
    return client.get_table(f"{database}.{table_name}")

@tool
def register_table_schema(schema: dict) -> str:
    """テーブルスキーマを OpenMetadata に登録する"""
    client = OpenMetadataClient()
    return client.create_or_update_table(schema)

schema_agent = create_react_agent(
    model=ChatOpenAI(
        base_url="http://vllm-service:8080/v1",
        model="ibm-granite-20b-code-instruct"
    ),
    tools=[get_table_schema, register_table_schema],
    system_prompt="""
    あなたはデータスキーマ管理の専門エージェントです。
    ユーザーのリクエストに従い、OpenMetadata のスキーマ情報を
    取得・登録・更新します。
    """
)
```

## Human-in-the-Loop パターン

```python
from langgraph.checkpoint.postgres import PostgresSaver

# チェックポイントを PostgreSQL に保存
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost/agentdb"
)

def human_approval_node(state: AgentState):
    """承認待ち状態でグラフを一時停止"""
    # Kafka に承認リクエストを発行
    kafka_producer.send("approval-requests", {
        "thread_id": state["thread_id"],
        "action": state["pending_action"],
        "requestor": state["user"],
    })
    # interrupt() で LangGraph が一時停止
    raise NodeInterrupt("承認待ち: Slack で承認してください")

# 承認後に再開
graph.invoke(
    {"approved": True},
    config={"configurable": {"thread_id": thread_id}},
)
```

## エージェント間通信

エージェント間の通信は LangGraph の State を通じて行います。Kafka は非同期通知（承認リクエスト、完了通知）に使用します。

```
同期通信: State 経由（LangGraph 内部）
非同期通知: Kafka トピック
  - approval-requests: 承認リクエスト
  - agent-completions: 完了通知
  - schema-changes: スキーマ変更通知
```
