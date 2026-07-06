from typing import Literal
import structlog
from langchain_core.tools import tool
from tools.common.client import get_openmetadata_client

log = structlog.get_logger()


@tool
def search_data_assets(
    query: str,
    asset_type: Literal["table", "topic", "pipeline", "data_product", "all"] = "all",
    limit: int = 10,
) -> dict:
    """
    OpenMetadata のデータ資産を自然言語クエリで検索します。

    Args:
        query: 検索クエリ (例: "顧客の注文履歴", "drone delivery")
        asset_type: 絞り込む資産タイプ。"table", "topic", "pipeline", "data_product", "all" のいずれか。
            「データプロダクト」を尋ねられた場合は必ず "data_product" を指定すること。
        limit: 最大取得件数 (1-100)
    """
    log.info("search_data_assets", query=query, asset_type=asset_type)
    # NOTE: description (特にデータプロダクト/契約情報) が非常に長い場合があり、
    # 未加工のまま複数件返すと vLLM の max-model-len (8192) を容易に超えるため切り詰める
    DESCRIPTION_MAX_CHARS = 150
    try:
        client = get_openmetadata_client()
        results = client.search_assets(query, asset_type, limit)
        assets = [_to_asset_dict(r, asset_type, DESCRIPTION_MAX_CHARS) for r in results]
        return {"assets": assets, "total": len(assets), "query": query, "success": True}
    except Exception as e:
        log.error("search_data_assets_failed", query=query, error=str(e))
        return {"error": f"検索エラー: {str(e)}", "success": False}


def _to_asset_dict(r: dict, default_type: str, description_max_chars: int) -> dict:
    # NOTE: OpenMetadata の owner フィールドは複数所有者対応のため
    # "owners" (配列) であり、旧来の単数形 "owner" ではない。
    owners = r.get("owners") or []
    return {
        "fqn": r.get("fullyQualifiedName", ""),
        "name": r.get("name", ""),
        "type": r.get("entityType", default_type),
        "description": (r.get("description", "") or "")[:description_max_chars],
        "tags": [t.get("tagFQN", "") for t in r.get("tags", [])],
        "owners": [o.get("displayName") or o.get("name", "") for o in owners],
        "updatedAt": r.get("updatedAt", ""),
    }


@tool
def get_recent_activity(limit: int = 10) -> dict:
    """
    最近更新されたデータ資産の一覧を取得します（更新日時の新しい順）。

    Args:
        limit: 最大取得件数 (1-100)
    """
    log.info("get_recent_activity", limit=limit)
    DESCRIPTION_MAX_CHARS = 150
    try:
        client = get_openmetadata_client()
        results = client.get_recent_activity(limit)
        assets = [_to_asset_dict(r, "all", DESCRIPTION_MAX_CHARS) for r in results]
        return {"assets": assets, "total": len(assets), "success": True}
    except Exception as e:
        log.error("get_recent_activity_failed", error=str(e))
        return {"error": f"取得エラー: {str(e)}", "success": False}


@tool
def get_my_data_assets(owner_name: str, limit: int = 10) -> dict:
    """
    指定したユーザー (オーナー) が所有するデータ資産の一覧を取得します。
    「マイデータ」「自分のデータ」を尋ねられた場合は、会話のユーザー名を
    owner_name に指定して呼び出すこと。

    Args:
        owner_name: オーナーのユーザー名 (例: "admin")
        limit: 最大取得件数 (1-100)
    """
    log.info("get_my_data_assets", owner_name=owner_name)
    DESCRIPTION_MAX_CHARS = 150
    try:
        client = get_openmetadata_client()
        results = client.get_owned_assets(owner_name, limit)
        assets = [_to_asset_dict(r, "all", DESCRIPTION_MAX_CHARS) for r in results]
        return {"assets": assets, "total": len(assets), "owner": owner_name, "success": True}
    except Exception as e:
        log.error("get_my_data_assets_failed", owner_name=owner_name, error=str(e))
        return {"error": f"取得エラー: {str(e)}", "success": False}
