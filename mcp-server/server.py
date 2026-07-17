"""MCP Tool サーバー本体。

README のガードレールアーキテクチャ図における「MCP Tool」を、Model Context
Protocol (streamable-http) で外部の MCP クライアントに公開する。Connectivity
Link (MCP Gateway) の HTTPRoute はこの Service (port 8000) を backend とする。

ここではビジネスロジックを実装せず、既存の LangChain @tool (tools/openmetadata/
search_tools.py) をそのまま呼び出す薄いラッパーのみを置く(Tool First / 重複実装
の回避)。
"""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from tools.openmetadata.search_tools import (
    get_my_data_assets,
    get_recent_activity,
    get_topic_sample_data,
    search_data_assets,
)

mcp = FastMCP("datamesh-mcp-server", host="0.0.0.0", port=8000)


@mcp.tool()
def search_data_assets_tool(
    query: str,
    asset_type: Literal["table", "topic", "pipeline", "data_product", "all"] = "all",
    limit: int = 10,
) -> dict:
    """OpenMetadata のデータ資産を自然言語クエリで検索する。"""
    return search_data_assets.invoke({"query": query, "asset_type": asset_type, "limit": limit})


@mcp.tool()
def get_recent_activity_tool(limit: int = 10) -> dict:
    """最近更新されたデータ資産の一覧を取得する(更新日時の新しい順)。"""
    return get_recent_activity.invoke({"limit": limit})


@mcp.tool()
def get_topic_sample_data_tool(topic_fqn: str, limit: int = 5) -> dict:
    """Kafka トピックのサンプルメッセージを取得する。"""
    return get_topic_sample_data.invoke({"topic_fqn": topic_fqn, "limit": limit})


@mcp.tool()
def get_my_data_assets_tool(owner_name: str, limit: int = 10) -> dict:
    """指定したオーナーが所有するデータ資産の一覧を取得する。"""
    return get_my_data_assets.invoke({"owner_name": owner_name, "limit": limit})


def build_app():
    """Starlette app に k8s liveness/readiness 用の /healthz を追加して返す。"""
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    app = mcp.streamable_http_app()
    app.router.routes.append(Route("/healthz", lambda request: PlainTextResponse("ok")))
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
