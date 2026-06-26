from pathlib import Path
from langgraph.prebuilt import create_react_agent
from agent.common.llm import get_llm
from tools.business import (
    register_customer,
    search_customers,
    get_customer,
    update_customer,
    register_bom,
    search_bom,
    get_bom,
)
from tools.openmetadata import search_data_assets

_SYSTEM_PROMPT = (Path(__file__).parent.parent.parent / "prompts/validation/system.md").read_text()

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


def create_registration_agent():
    return create_react_agent(
        model=get_llm(),
        tools=REGISTRATION_TOOLS,
        state_modifier=_SYSTEM_PROMPT,
    )
