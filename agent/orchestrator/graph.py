import contextvars
import structlog
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END

from agent.common.state import AgentState
from agent.common.llm import get_llm, sum_tokens
from agent.orchestrator.router import classify_intent, route_to_agent
from agent.schema_agent.agent import create_schema_agent
from agent.search_agent.agent import create_search_agent
from agent.registration_agent.agent import create_registration_agent

log = structlog.get_logger()

# エージェントファクトリ（初回呼び出し時に生成）
_AGENTS: dict = {}


def _get_agent(name: str):
    if name not in _AGENTS:
        factories = {
            "schema":       create_schema_agent,
            "search":       create_search_agent,
            "registration": create_registration_agent,
        }
        _AGENTS[name] = factories[name]()
    return _AGENTS[name]


# NOTE: AgentState["messages"] は Annotated[list, operator.add] で
# チェックポインタ経由で会話全体を蓄積し続けるため、長い会話では
# vLLM の max-model-len (8192) を超えて 400 エラーになる。LLM へ渡す
# 直前には必ず直近 N 件だけに絞ること。
RECENT_MESSAGES_LIMIT = 10


def _recent_messages(state: AgentState) -> list:
    messages = state["messages"]
    return messages[-RECENT_MESSAGES_LIMIT:] if len(messages) > RECENT_MESSAGES_LIMIT else messages


# NOTE: config["configurable"] 経由で status キューを渡そうとしたが、
# PostgresSaver チェックポインタ付きでコンパイルしたグラフでは
# configurable がチェックポインタの識別キー以外を除去してしまい、
# ノード関数まで届かないことが判明した (contextvars ならスレッド内の
# 呼び出しスタックに伝播するため、チェックポインタの介在を受けない)。
_status_queue_var: contextvars.ContextVar = contextvars.ContextVar(
    "status_queue", default=None
)

# ツール名 -> 検索中表示用の日本語ラベル (「意図を判定しています」だけでは
# 何をしているか分からないという要望を受け、サブエージェント内のツール
# 呼び出し単位でも status キューへ通知する)
_TOOL_STATUS_LABELS = {
    "search_data_assets":     "OpenMetadata でデータ資産を検索しています...",
    "get_recent_activity":    "OpenMetadata の最近の更新をクロールしています...",
    "get_my_data_assets":     "OpenMetadata でオーナー別データを検索しています...",
    "get_database_schema":    "テーブルのスキーマ情報を取得しています...",
    "list_tables":            "テーブル一覧を取得しています...",
    "register_table_metadata": "テーブルメタデータを登録しています...",
    "update_column_description": "カラムの説明を更新しています...",
    "get_data_lineage":       "データリネージを辿っています...",
    "get_quality_metrics":    "データ品質メトリクスを取得しています...",
    "create_quality_rule":    "データ品質ルールを作成しています...",
    "search_customers":       "顧客情報を検索しています...",
    "search_bom":             "BOM情報を検索しています...",
}


def _invoke_subagent(agent, input_messages: list) -> dict:
    """create_react_agent のツール呼び出しループを stream() で実行し、
    実際に呼ばれたツール名を status キューへ逐次通知する。
    NOTE: stream(stream_mode="updates") は各ノードの新規メッセージだけを
    返すため、invoke() 相当の全メッセージ列は手動で積み上げる
    (再度 invoke() し直すとツール呼び出しの副作用が二重実行されてしまう)。"""
    status_q = _status_queue_var.get()
    accumulated = list(input_messages)
    for chunk in agent.stream({"messages": input_messages}, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            if not isinstance(node_output, dict):
                continue
            new_messages = node_output.get("messages", [])
            accumulated.extend(new_messages)
            if status_q and node_name == "tools":
                for msg in new_messages:
                    tool_name = getattr(msg, "name", None)
                    if tool_name:
                        status_q.put(
                            _TOOL_STATUS_LABELS.get(tool_name, f"{tool_name} を実行しています...")
                        )
    return {"messages": accumulated}


def intent_classifier_node(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    text = last_message.content if hasattr(last_message, "content") else str(last_message)
    intent = classify_intent(text)
    log.info("intent_classified", intent=intent, thread_id=state.get("thread_id"))
    return {"intent": intent}


def chitchat_node(state: AgentState) -> dict:
    # NOTE: tools を一切バインドしない生の LLM 呼び出しのため、tool_choice="auto" を
    # 指定していても物理的にツール呼び出しが発生しえない (ReAct ループを完全に回避)。
    # 挨拶・雑談は毎回確実に高速応答させるためのショートカット経路。
    log.info("chitchat_invoked", thread_id=state.get("thread_id"))
    llm = get_llm()
    ai_message = llm.invoke(_recent_messages(state))
    return {
        "messages": [ai_message],
        "active_agent": "chitchat",
        "agent_output": {"messages": [ai_message.content]},
        "token_usage": sum_tokens([ai_message]),
    }


def _invoke_subagent_ensured(agent, input_messages: list) -> list:
    """サブエージェントを実行し、必ず1件以上の新規メッセージを返す。

    同時アクセスで vLLM が混雑すると2回目の応答生成(ツール結果を受けての
    最終応答)が空文字を返してくることがあり(例外は発生しない)、その場合は
    同じ入力で再試行する。全て空ならフォールバックのAIMessageを返し、
    呼び出し側の result["messages"][-1] が IndexError にならないようにする。"""
    from langchain_core.messages import AIMessage

    for attempt in range(3):
        result = _invoke_subagent(agent, input_messages)
        new_messages = result["messages"][len(input_messages):]
        if new_messages:
            return new_messages
        log.warning("subagent_empty_reply_retry", attempt=attempt)
    return [AIMessage(content="すみません、処理中にエラーが発生しました。もう一度お試しください。")]


def schema_agent_node(state: AgentState) -> dict:
    log.info("schema_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("schema")
    input_messages = _recent_messages(state)
    new_messages = _invoke_subagent_ensured(agent, input_messages)
    return {
        "messages": new_messages,
        "active_agent": "schema",
        "agent_output": {"messages": [new_messages[-1].content]},
        "token_usage": sum_tokens(new_messages),
    }


def _build_user_context_message(state: AgentState) -> SystemMessage | None:
    user_id = state.get("user_id")
    if not user_id or user_id == "anonymous":
        return None
    # NOTE: Keycloak の "admin" ロールを持つユーザーは、OpenMetadata 側の
    # 実ユーザー名 "admin" のデータオーナーとして扱う (このワークショップ環境の
    # OpenMetadata データは全て "admin" ユーザーが所有者として登録されているため)。
    is_admin = "admin" in (state.get("user_roles") or [])
    owner_name = "admin" if is_admin else user_id
    return SystemMessage(
        content=(
            f"[context] ログイン中のユーザー名: {user_id}"
            f"{' (OpenMetadata 管理者権限あり)' if is_admin else ''}\n"
            f"「マイデータ」「自分のデータ」を尋ねられた場合は "
            f"get_my_data_assets を owner_name=\"{owner_name}\" で呼び出すこと。"
        )
    )


def search_agent_node(state: AgentState) -> dict:
    log.info("search_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("search")
    context_msg = _build_user_context_message(state)
    input_messages = ([context_msg] if context_msg else []) + _recent_messages(state)
    new_messages = _invoke_subagent_ensured(agent, input_messages)
    return {
        "messages": new_messages,
        "active_agent": "search",
        "agent_output": {"messages": [new_messages[-1].content]},
        "token_usage": sum_tokens(new_messages),
    }


def registration_agent_node(state: AgentState) -> dict:
    log.info("registration_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("registration")
    input_messages = _recent_messages(state)
    output_messages = _invoke_subagent_ensured(agent, input_messages)

    # 承認フラグの検出（レスポンスに「承認」キーワードが含まれるか）
    last_content = output_messages[-1].content
    requires_approval = "承認" in last_content or "confirm" in last_content.lower()

    return {
        "messages": output_messages,
        "active_agent": "registration",
        "requires_approval": requires_approval,
        "approval_action": last_content if requires_approval else "",
        "agent_output": {"messages": [m.content for m in output_messages[-1:]]},
        "token_usage": sum_tokens(output_messages),
    }


def human_approval_node(state: AgentState) -> dict:
    from langgraph.errors import NodeInterrupt
    log.info("waiting_for_approval", thread_id=state.get("thread_id"))
    raise NodeInterrupt(
        f"承認が必要です。以下の操作を承認してください:\n{state.get('approval_action', '')}"
    )


def _check_approval(state: AgentState) -> str:
    if state.get("requires_approval"):
        return "needs_approval"
    return "done"


def create_graph(checkpointer=None) -> object:
    graph = StateGraph(AgentState)

    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("chitchat", chitchat_node)
    graph.add_node("schema_agent", schema_agent_node)
    graph.add_node("search_agent", search_agent_node)
    graph.add_node("registration_agent", registration_agent_node)
    graph.add_node("human_approval", human_approval_node)

    graph.set_entry_point("intent_classifier")

    graph.add_conditional_edges(
        "intent_classifier",
        route_to_agent,
        {
            "chitchat":     "chitchat",
            "schema":       "schema_agent",
            "search":       "search_agent",
            "registration": "registration_agent",
        },
    )

    graph.add_edge("chitchat", END)
    graph.add_edge("schema_agent", END)
    graph.add_edge("search_agent", END)

    graph.add_conditional_edges(
        "registration_agent",
        _check_approval,
        {
            "done":          END,
            "needs_approval": "human_approval",
        },
    )

    graph.add_edge("human_approval", END)

    if checkpointer:
        checkpointer.setup()
        return graph.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])

    return graph.compile()
