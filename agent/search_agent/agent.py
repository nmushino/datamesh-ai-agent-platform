from pathlib import Path
from langgraph.prebuilt import create_react_agent
from agent.common.llm import get_llm
from tools.openmetadata import (
    search_data_assets,
    get_recent_activity,
    get_my_data_assets,
    get_topic_sample_data,
    get_database_schema,
    get_data_lineage,
    get_quality_metrics,
)
from tools.business import search_customers, search_bom

SYSTEM_PROMPT = (Path(__file__).parent.parent.parent / "prompts/search/system.md").read_text()

SEARCH_TOOLS = [
    search_data_assets,
    get_recent_activity,
    get_my_data_assets,
    get_topic_sample_data,
    get_database_schema,
    get_data_lineage,
    get_quality_metrics,
    search_customers,
    search_bom,
]


def create_search_agent(enable_thinking: bool = False, max_tokens: int = 1024):
    return create_react_agent(
        model=get_llm(enable_thinking=enable_thinking, max_tokens=max_tokens),
        tools=SEARCH_TOOLS,
        state_modifier=SYSTEM_PROMPT,
    )
