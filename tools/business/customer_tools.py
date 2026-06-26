import structlog
import httpx
from langchain_core.tools import tool
from tools.common.client import get_business_api_client

log = structlog.get_logger()


@tool
def register_customer(
    customer_id: str,
    name: str,
    email: str,
    phone: str = "",
    address: str = "",
) -> dict:
    """
    Quarkus Business API を通じて顧客を登録します。
    登録後、OpenMetadata にもメタデータが非同期で同期されます。

    Args:
        customer_id: 顧客 ID (形式: CUST-XXXXXXXX)
        name: 顧客名（氏名）
        email: メールアドレス
        phone: 電話番号（任意）
        address: 住所（任意）

    Returns:
        {"customerId": str, "name": str, "registeredAt": str, "success": bool}
    """
    log.info("register_customer", customer_id=customer_id)
    try:
        client = get_business_api_client()
        result = client.post("/api/v1/customers", {
            "customerId": customer_id,
            "name": name,
            "email": email,
            "phone": phone,
            "address": address,
        })
        return {**result, "success": True}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            return {"error": f"顧客 ID が既に存在します: {customer_id}", "success": False}
        if e.response.status_code == 400:
            detail = e.response.json().get("message", "入力値が不正です")
            return {"error": detail, "success": False}
        log.error("register_customer_failed", status=e.response.status_code, error=str(e))
        return {"error": f"API エラー: {e.response.status_code}", "success": False}
    except httpx.RequestError as e:
        log.error("register_customer_connection_error", error=str(e))
        return {"error": "Business API に接続できません", "success": False}


@tool
def search_customers(
    query: str,
    status: str = "",
    limit: int = 20,
) -> dict:
    """
    顧客データを検索します。

    Args:
        query: 検索クエリ（顧客名・メールアドレス・顧客IDで検索）
        status: ステータスフィルタ ("active", "inactive", "" で全件)
        limit: 最大取得件数

    Returns:
        {"customers": [{"customerId": str, "name": str, "email": str, "status": str}],
         "total": int, "success": bool}
    """
    log.info("search_customers", query=query)
    try:
        client = get_business_api_client()
        params = {"q": query, "limit": limit}
        if status:
            params["status"] = status
        result = client.get("/api/v1/customers/search", params)
        return {**result, "success": True}
    except httpx.RequestError as e:
        return {"error": "Business API に接続できません", "success": False}
    except Exception as e:
        log.error("search_customers_failed", error=str(e))
        return {"error": str(e), "success": False}


@tool
def get_customer(customer_id: str) -> dict:
    """
    顧客 ID で顧客情報を取得します。

    Args:
        customer_id: 顧客 ID

    Returns:
        顧客情報の辞書、または {"error": str, "success": False}
    """
    try:
        client = get_business_api_client()
        result = client.get(f"/api/v1/customers/{customer_id}")
        return {**result, "success": True}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"顧客が見つかりません: {customer_id}", "success": False}
        return {"error": f"API エラー: {e.response.status_code}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


@tool
def update_customer(
    customer_id: str,
    name: str = "",
    email: str = "",
    phone: str = "",
    address: str = "",
    status: str = "",
) -> dict:
    """
    顧客情報を更新します。指定したフィールドのみ更新されます。

    Args:
        customer_id: 顧客 ID
        name: 新しい顧客名（省略可）
        email: 新しいメールアドレス（省略可）
        phone: 新しい電話番号（省略可）
        address: 新しい住所（省略可）
        status: 新しいステータス ("active", "inactive")（省略可）

    Returns:
        {"customerId": str, "updated": bool, "success": bool}
    """
    log.info("update_customer", customer_id=customer_id)
    try:
        client = get_business_api_client()
        payload = {k: v for k, v in {
            "name": name, "email": email, "phone": phone,
            "address": address, "status": status,
        }.items() if v}
        result = client.patch(f"/api/v1/customers/{customer_id}", payload)
        return {**result, "updated": True, "success": True}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"顧客が見つかりません: {customer_id}", "success": False}
        return {"error": f"API エラー: {e.response.status_code}", "success": False}
    except Exception as e:
        log.error("update_customer_failed", error=str(e))
        return {"error": str(e), "success": False}
