import os
from functools import lru_cache
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
