import structlog
from langchain_core.tools import tool

from tools.common.history_store import get_history_store

log = structlog.get_logger()


@tool
def search_conversation_history(owner_name: str, query: str, limit: int = 5) -> dict:
    """
    そのユーザーの過去の会話履歴(以前の質問・回答)をキーワードで検索します。
    「前に聞いた〇〇について」「以前の会話で△△と言っていた件」のように、
    過去のやり取りを参照する必要がある依頼で使うこと。

    Args:
        owner_name: 会話コンテキストのユーザー名
        query: 検索キーワード(部分一致)
        limit: 最大取得件数 (1-20)
    """
    log.info("search_conversation_history", owner_name=owner_name, query=query)
    store = get_history_store()
    if store is None:
        return {"error": "会話履歴ストアが利用できません", "success": False}
    try:
        results = store.search(owner_name, query, limit)
        return {"results": results, "total": len(results), "success": True}
    except Exception as e:
        log.error("search_conversation_history_failed", error=str(e))
        return {"error": f"検索エラー: {str(e)}", "success": False}
