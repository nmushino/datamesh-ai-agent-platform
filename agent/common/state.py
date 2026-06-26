from typing import Annotated, TypedDict
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    intent: str
    active_agent: str
    agent_output: dict
    requires_approval: bool
    approval_action: str
    thread_id: str
    user_id: str
    user_roles: list[str]
