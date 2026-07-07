from pathlib import Path
from langgraph.prebuilt import create_react_agent
from agent.common.llm import get_llm
from tools.openmetadata import (
    get_database_schema,
    list_tables,
    register_table_metadata,
    register_topic_metadata,
    register_glossary_term,
    update_column_description,
    create_quality_rule,
)
from tools.kafka import create_kafka_topic
from tools.github import (
    find_github_files_by_name,
    get_github_file_content,
    get_github_readme,
    list_github_org_repos,
)

SYSTEM_PROMPT = (Path(__file__).parent.parent.parent / "prompts/schema/system.md").read_text()

SCHEMA_TOOLS = [
    get_database_schema,
    list_tables,
    register_table_metadata,
    register_topic_metadata,
    register_glossary_term,
    create_kafka_topic,
    update_column_description,
    create_quality_rule,
    find_github_files_by_name,
    get_github_file_content,
    get_github_readme,
    list_github_org_repos,
]

# 実ブローカーへの書き込みを伴うため承認必須 (orchestrator の human_approval_node で参照)
APPROVAL_REQUIRED_TOOLS = {"create_kafka_topic"}


def create_schema_agent(enable_thinking: bool = False, max_tokens: int = 1024):
    return create_react_agent(
        model=get_llm(enable_thinking=enable_thinking, max_tokens=max_tokens),
        tools=SCHEMA_TOOLS,
        state_modifier=SYSTEM_PROMPT,
    )
