from typing import Literal
import structlog
from langchain_core.tools import tool
from tools.common.client import get_openmetadata_client

log = structlog.get_logger()


@tool
def search_data_assets(
    query: str,
    asset_type: Literal["table", "topic", "pipeline", "all"] = "all",
    limit: int = 10,
) -> dict:
    """
    OpenMetadata のデータ資産を自然言語クエリで検索します。

    Args:
        query: 検索クエリ (例: "顧客の注文履歴", "drone delivery")
        asset_type: 絞り込む資産タイプ。"table", "topic", "pipeline", "all" のいずれか
        limit: 最大取得件数 (1-100)

    Returns:
        {"assets": [{"fqn": str, "name": str, "type": str, "description": str, "tags": list}],
         "total": int, "success": bool}
    """
    log.info("search_data_assets", query=query, asset_type=asset_type)
    # NOTE: description (特にデータプロダクト/契約情報) が非常に長い場合があり、
    # 未加工のまま複数件返すと vLLM の max-model-len (8192) を容易に超えるため切り詰める
    DESCRIPTION_MAX_CHARS = 300
    try:
        client = get_openmetadata_client()
        results = client.search_assets(query, asset_type, limit)
        assets = [
            {
                "fqn": r.get("fullyQualifiedName", ""),
                "name": r.get("name", ""),
                "type": r.get("entityType", asset_type),
                "description": (r.get("description", "") or "")[:DESCRIPTION_MAX_CHARS],
                "tags": [t.get("tagFQN", "") for t in r.get("tags", [])],
                "owner": r.get("owner", {}).get("name", "") if r.get("owner") else "",
                "updatedAt": r.get("updatedAt", ""),
            }
            for r in results
        ]
        return {"assets": assets, "total": len(assets), "query": query, "success": True}
    except Exception as e:
        log.error("search_data_assets_failed", query=query, error=str(e))
        return {"error": f"検索エラー: {str(e)}", "success": False}
