import httpx
import structlog
from langchain_core.tools import tool

from tools.common.client import get_business_api_client

log = structlog.get_logger()


@tool
def register_bom(
    bom_id: str,
    product_name: str,
    components: list[dict],
    version: str = "1.0",
    description: str = "",
) -> dict:
    """
    部品表 (BOM: Bill of Materials) を登録します。

    Args:
        bom_id: BOM ID (形式: BOM-XXXXXXXX)
        product_name: 製品名
        components: 部品リスト
            例: [{"partNumber": "PART-001", "name": "モーター", "quantity": 4}]
        version: BOM バージョン (デフォルト: "1.0")
        description: BOM の説明（任意）
    """
    log.info("register_bom", bom_id=bom_id, product=product_name)
    try:
        client = get_business_api_client()
        result = client.post("/api/v1/bom", {
            "bomId": bom_id,
            "productName": product_name,
            "version": version,
            "description": description,
            "components": components,
        })
        return {**result, "success": True}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return {"error": f"BOM ID が既に存在します: {bom_id}", "success": False}
        return {"error": f"API エラー: {e.response.status_code}", "success": False}
    except httpx.RequestError:
        return {"error": "Business API に接続できません", "success": False}


@tool
def search_bom(
    query: str,
    product_name: str = "",
    limit: int = 20,
) -> dict:
    """
    BOM データを検索します。

    Args:
        query: 検索クエリ（BOM ID・製品名・部品番号で検索）
        product_name: 製品名フィルタ（任意）
        limit: 最大取得件数
    """
    try:
        client = get_business_api_client()
        params = {"q": query, "limit": limit}
        if product_name:
            params["productName"] = product_name
        result = client.get("/api/v1/bom/search", params)
        return {**result, "success": True}
    except Exception as e:
        log.error("search_bom_failed", error=str(e))
        return {"error": str(e), "success": False}


@tool
def get_bom(bom_id: str) -> dict:
    """
    BOM ID で BOM 情報を取得します（部品リストを含む）。

    Args:
        bom_id: BOM ID
    """
    try:
        client = get_business_api_client()
        result = client.get(f"/api/v1/bom/{bom_id}")
        return {**result, "success": True}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"BOM が見つかりません: {bom_id}", "success": False}
        return {"error": f"API エラー: {e.response.status_code}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}
