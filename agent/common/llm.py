import os
from functools import lru_cache
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


# チャット画面から選べる max_tokens の4段階 (表示ラベル -> 実際のトークン数)
MAX_TOKENS_LEVELS = {
    "low": 1024,
    "medium": 2048,
    "high": 4096,
    "max": 8192,
}
DEFAULT_MAX_TOKENS_LEVEL = "low"


@lru_cache(maxsize=16)
def get_llm(
    model: str | None = None,
    temperature: float = 0,
    enable_thinking: bool = False,
    max_tokens: int = 1024,
) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ["VLLM_BASE_URL"],
        api_key=os.getenv("VLLM_API_KEY", "not-needed"),
        model=model or os.environ["VLLM_MODEL"],
        temperature=temperature,
        max_tokens=max_tokens,
        # Qwen3のthinking mode(<think>...</think>の推論トレース)はチャット画面の
        # トグルでオン/オフを選べるようにする(デフォルトはOFF: CPU/単一GPU推論では
        # 応答時間を大幅に伸ばすため)。
        # temperature=0 (greedy) はrepetition_penalty無しだと同じフレーズを
        # 繰り返す暴走生成に陥ることがあり(実際に26万文字超の出力を観測)、
        # 応答時間の悪化と空応答フォールバックの一因になっていたため抑制する。
        extra_body={
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
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
