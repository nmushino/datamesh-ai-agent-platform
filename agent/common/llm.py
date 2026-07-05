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
        max_tokens=1024,
        # Qwen3のthinking mode(<think>...</think>の推論トレース)はCPU推論では
        # 応答時間を大幅に伸ばすため無効化する。
        # temperature=0 (greedy) はrepetition_penalty無しだと同じフレーズを
        # 繰り返す暴走生成に陥ることがあり(実際に26万文字超の出力を観測)、
        # 応答時間の悪化と空応答フォールバックの一因になっていたため抑制する。
        extra_body={
            "chat_template_kwargs": {"enable_thinking": False},
            "repetition_penalty": 1.1,
        },
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
