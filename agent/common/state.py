from typing import Annotated, TypedDict
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    intent: str
    # 意図判定の根拠になった正規表現パターン(ステータス表示用、chitchat等ではなし)
    matched_pattern: str
    active_agent: str
    agent_output: dict
    requires_approval: bool
    approval_action: str
    thread_id: str
    user_id: str
    user_roles: list[str]
    # Annotatedなし(累積せず毎ターン上書き) = このターンで使用したトークン数のみを保持する
    token_usage: int
    # チャット画面から毎回選べるLLM設定 (Thinkingモードのオン/オフ、max_tokensの段階)
    enable_thinking: bool
    max_tokens: int
