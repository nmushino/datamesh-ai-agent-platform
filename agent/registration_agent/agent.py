from pathlib import Path

from langgraph.prebuilt import create_react_agent

from agent.common.llm import get_llm
from tools.business import (
    get_bom,
    get_customer,
    register_bom,
    register_customer,
    search_bom,
    search_customers,
    update_customer,
)
from tools.openmetadata import search_data_assets

SYSTEM_PROMPT = (Path(__file__).parent.parent.parent / "prompts/validation/system.md").read_text()

REGISTRATION_TOOLS = [
    register_customer,
    search_customers,
    get_customer,
    update_customer,
    register_bom,
    search_bom,
    get_bom,
    search_data_assets,
]

# 承認が必要な Tool 名のセット
APPROVAL_REQUIRED_TOOLS = {"update_customer", "register_bom"}


def create_registration_agent(enable_thinking: bool = False, max_tokens: int = 1024):
    return create_react_agent(
        model=get_llm(enable_thinking=enable_thinking, max_tokens=max_tokens),
        tools=REGISTRATION_TOOLS,
        state_modifier=SYSTEM_PROMPT,
    )
