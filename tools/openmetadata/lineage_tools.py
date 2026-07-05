import structlog
from langchain_core.tools import tool
from tools.common.client import get_openmetadata_client

log = structlog.get_logger()


@tool
def get_data_lineage(fqn: str, depth: int = 3) -> dict:
    """
    データリネージ（データの流れ）を取得します。

    Args:
        fqn: 起点となるエンティティの完全修飾名
             (例: "postgresql-prod.dronedb.public.orders")
        depth: リネージの深さ (1-5)。大きいほど広範囲を取得

    Returns:
        {
          "fqn": str,
          "upstream": [{"fqn": str, "name": str, "type": str}],
          "downstream": [{"fqn": str, "name": str, "type": str}],
          "success": bool
        }
    """
    log.info("get_data_lineage", fqn=fqn, depth=depth)
    try:
        client = get_openmetadata_client()
        lineage = client.get_lineage(fqn, depth=min(depth, 5))

        def extract_nodes(edges: list, direction: str) -> list[dict]:
            nodes = []
            for edge in edges:
                node = edge.get("toEntity" if direction == "downstream" else "fromEntity", {})
                if node:
                    nodes.append({
                        "fqn": node.get("fullyQualifiedName", ""),
                        "name": node.get("name", ""),
                        "type": node.get("type", ""),
                    })
            return nodes

        return {
            "fqn": fqn,
            "upstream": extract_nodes(lineage.get("upstreamEdges", []), "upstream"),
            "downstream": extract_nodes(lineage.get("downstreamEdges", []), "downstream"),
            "success": True,
        }
    except ValueError as e:
        return {"error": str(e), "success": False}
    except Exception as e:
        log.error("get_data_lineage_failed", fqn=fqn, error=str(e))
        return {"error": f"リネージ取得エラー: {str(e)}", "success": False}
