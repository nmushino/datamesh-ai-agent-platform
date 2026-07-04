import os
from functools import lru_cache
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


@lru_cache(maxsize=4)
def get_llm(model: str | None = None, temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ["VLLM_BASE_URL"],
        api_key=os.getenv("VLLM_API_KEY", "not-needed"),
        model=model or os.environ["VLLM_MODEL"],
        temperature=temperature,
        max_tokens=2048,
        # Qwen3のthinking mode(<think>...</think>の推論トレース)はCPU推論では
        # 応答時間を大幅に伸ばすため無効化する
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def sum_tokens(messages: list[BaseMessage]) -> int:
    """create_react_agentのツール呼び出しループでは複数回LLMを呼ぶことがあるため、
    このターンで新規に生成された全メッセージのトークン数を合算する"""
    total = 0
    for m in messages:
        usage = getattr(m, "usage_metadata", None)
        if usage:
            total += usage.get("total_tokens", 0)
    return total
