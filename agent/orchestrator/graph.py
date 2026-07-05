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


def schema_agent_node(state: AgentState) -> dict:
    log.info("schema_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("schema")
    input_messages = _recent_messages(state)
    result = agent.invoke({"messages": input_messages})
    new_messages = result["messages"][len(input_messages):]
    return {
        "messages": new_messages,
        "active_agent": "schema",
        "agent_output": {"messages": [m.content for m in result["messages"][-1:]]},
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
    result = agent.invoke({"messages": input_messages})
    new_messages = result["messages"][len(input_messages):]
    return {
        "messages": new_messages,
        "active_agent": "search",
        "agent_output": {"messages": [m.content for m in result["messages"][-1:]]},
        "token_usage": sum_tokens(new_messages),
    }


def registration_agent_node(state: AgentState) -> dict:
    log.info("registration_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("registration")
    input_messages = _recent_messages(state)
    result = agent.invoke({"messages": input_messages})
    output_messages = result["messages"][len(input_messages):]

    # 承認フラグの検出（レスポンスに「承認」キーワードが含まれるか）
    last_content = result["messages"][-1].content if result["messages"] else ""
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
