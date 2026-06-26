import os
import structlog
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from agent.common.state import AgentState
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


def intent_classifier_node(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    text = last_message.content if hasattr(last_message, "content") else str(last_message)
    intent = classify_intent(text)
    log.info("intent_classified", intent=intent, thread_id=state.get("thread_id"))
    return {"intent": intent}


def schema_agent_node(state: AgentState) -> dict:
    log.info("schema_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("schema")
    result = agent.invoke({"messages": state["messages"]})
    return {
        "messages": result["messages"][len(state["messages"]):],
        "active_agent": "schema",
        "agent_output": {"messages": [m.content for m in result["messages"][-1:]]},
    }


def search_agent_node(state: AgentState) -> dict:
    log.info("search_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("search")
    result = agent.invoke({"messages": state["messages"]})
    return {
        "messages": result["messages"][len(state["messages"]):],
        "active_agent": "search",
        "agent_output": {"messages": [m.content for m in result["messages"][-1:]]},
    }


def registration_agent_node(state: AgentState) -> dict:
    log.info("registration_agent_invoked", thread_id=state.get("thread_id"))
    agent = _get_agent("registration")
    result = agent.invoke({"messages": state["messages"]})
    output_messages = result["messages"][len(state["messages"]):]

    # 承認フラグの検出（レスポンスに「承認」キーワードが含まれるか）
    last_content = result["messages"][-1].content if result["messages"] else ""
    requires_approval = "承認" in last_content or "confirm" in last_content.lower()

    return {
        "messages": output_messages,
        "active_agent": "registration",
        "requires_approval": requires_approval,
        "approval_action": last_content if requires_approval else "",
        "agent_output": {"messages": [m.content for m in output_messages[-1:]]},
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


def create_graph(db_url: str | None = None) -> object:
    graph = StateGraph(AgentState)

    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("schema_agent", schema_agent_node)
    graph.add_node("search_agent", search_agent_node)
    graph.add_node("registration_agent", registration_agent_node)
    graph.add_node("human_approval", human_approval_node)

    graph.set_entry_point("intent_classifier")

    graph.add_conditional_edges(
        "intent_classifier",
        route_to_agent,
        {
            "schema":       "schema_agent",
            "search":       "search_agent",
            "registration": "registration_agent",
        },
    )

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

    url = db_url or os.environ.get("AGENT_DB_URL")
    if url:
        checkpointer = PostgresSaver.from_conn_string(url)
        checkpointer.setup()
        return graph.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])

    return graph.compile()
