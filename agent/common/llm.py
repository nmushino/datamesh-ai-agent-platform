import os

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

# vLLM 起動時の --max-model-len。入力(システムプロンプト+会話履歴+ツール結果)
# と出力(max_tokens)の合計がこれを超えると 400 エラーになるか、応答生成の
# 余地が無くなって空応答/ツール結果そのままの表示に陥る。
MODEL_MAX_LEN = 32768

# 入力側に最低限確保しておく余白。システムプロンプト単体で数百トークン、
# ツール結果を含む会話履歴で数千トークンに達することがあるため、
# 出力用の max_tokens はこれを差し引いた範囲に収める。
INPUT_HEADROOM_TOKENS = 4096

# チャット画面から選べる max_tokens の4段階 (表示ラベル -> 実際のトークン数)。
# 以前は "max" が 8192 (= MODEL_MAX_LEN 全体) になっており、入力側の余地が
# ゼロになって常に失敗する(ツール結果の生JSONがそのまま返る)設定になっていた。
MAX_TOKENS_LEVELS = {
    "low": 1024,
    "medium": 2048,
    "high": 3072,
    "max": MODEL_MAX_LEN - INPUT_HEADROOM_TOKENS,
}
DEFAULT_MAX_TOKENS_LEVEL = "low"


def get_llm(
    model: str | None = None,
    temperature: float = 0,
    enable_thinking: bool = False,
    max_tokens: int = 1024,
) -> ChatOpenAI:
    # 呼び出し元の値に関わらず、入力側の余地がゼロにならないよう安全上限で
    # クランプする(MAX_TOKENS_LEVELS 以外の経路から呼ばれる場合の防御)。
    max_tokens = min(max_tokens, MODEL_MAX_LEN - INPUT_HEADROOM_TOKENS)
    # NOTE: 以前は @lru_cache で ChatOpenAI インスタンス(と内部のhttpxコネクション
    # プール)を使い回していたが、LangGraph のグラフ実行(checkpointerの有無を問わず
    # StateGraph.stream() 経由でノード関数を呼ぶ場合)内で同一クライアントを共有すると、
    # vLLM側は正常に応答を生成しているのに最終メッセージが空になる現象が発生した
    # (直接関数呼び出しでは再現せず)。LangGraphのノード実行に伴うスレッド境界を
    # 跨いだコネクション共有が疑われるため、毎回新規のクライアントを生成する。
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
