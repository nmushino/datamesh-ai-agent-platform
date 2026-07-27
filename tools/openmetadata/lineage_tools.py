import structlog
from langchain_core.tools import tool

from tools.common.client import get_openmetadata_client

log = structlog.get_logger()


@tool
def get_data_lineage(fqn: str, depth: int = 3) -> dict:
    """
    データリネージ（データの流れ）を取得します。

    Args:
        fqn: 起点となるエンティティの完全修飾名。実在の値が不明な場合は
             先に search_data_assets で検索して確認すること
             (例: "external-shop-cluster-postgres-asite:5432.droneshopdb.droneshop.orders")
        depth: リネージの深さ (1-5)。大きいほど広範囲を取得
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
        return {"error": f"リネージ取得エラー: {e!s}", "success": False}


@tool
def add_data_lineage(
    from_entity_type: str,
    from_fqn: str,
    to_entity_type: str,
    to_fqn: str,
    description: str | None = None,
) -> dict:
    """
    2つのデータ資産の間にリネージ(データの流れ)を手動で追加します。
    Kafkaトピックはこの環境に自動でリネージを生成する仕組みが無いため
    (テーブルのようなSQLクエリログ解析によるリネージ推定はKafkaには
    適用されない)、GitHub上のソースコード調査で実際のpublish/subscribe
    関係が確認できた場合に、このツールで手動登録する。

    リネージの向き(from → to)は必ず「データが流れる方向」にすること
    (例: 注文を受け付けるトピック → それを読んで加工した結果を送信する
    トピック)。憶測でトポロジーを作らず、find_github_files_by_name /
    get_github_file_content で実際にコンシューマ/プロデューサの
    コードを確認してから呼ぶこと。

    Args:
        from_entity_type: 起点(上流)のエンティティ種別。
            "topic" / "table" / "pipeline" / "dashboard" / "dataProduct" のいずれか
        from_fqn: 起点の完全修飾名 (例: "external-shop-cluster-kafka-asite:9094.orders-in")
        to_entity_type: 終点(下流)のエンティティ種別。from_entity_type と同じ選択肢
        to_fqn: 終点の完全修飾名
        description: このリネージの根拠(参照したファイル名・処理内容の要約)。
            推測ではなく実際にコードで確認した内容を書くこと
    """
    log.info(
        "add_data_lineage",
        from_entity_type=from_entity_type, from_fqn=from_fqn,
        to_entity_type=to_entity_type, to_fqn=to_fqn,
    )
    try:
        client = get_openmetadata_client()
        result = client.add_lineage_edge(from_entity_type, from_fqn, to_entity_type, to_fqn, description)
        return {
            "from_fqn": from_fqn, "to_fqn": to_fqn, "created": True, "result": result, "success": True,
        }
    except ValueError as e:
        return {"error": str(e), "success": False}
    except Exception as e:
        log.error("add_data_lineage_failed", from_fqn=from_fqn, to_fqn=to_fqn, error=str(e))
        return {"error": f"リネージ追加エラー: {e!s}", "success": False}


@tool
def remove_data_lineage(
    from_entity_type: str, from_fqn: str, to_entity_type: str, to_fqn: str,
) -> dict:
    """
    add_data_lineage で誤って追加したリネージ、または実態と合わなくなった
    リネージを削除します。

    Args:
        from_entity_type: 起点のエンティティ種別 ("topic" / "table" / "pipeline" /
            "dashboard" / "dataProduct")
        from_fqn: 起点の完全修飾名
        to_entity_type: 終点のエンティティ種別
        to_fqn: 終点の完全修飾名
    """
    log.info(
        "remove_data_lineage",
        from_entity_type=from_entity_type, from_fqn=from_fqn,
        to_entity_type=to_entity_type, to_fqn=to_fqn,
    )
    try:
        client = get_openmetadata_client()
        client.remove_lineage_edge(from_entity_type, from_fqn, to_entity_type, to_fqn)
        return {"from_fqn": from_fqn, "to_fqn": to_fqn, "removed": True, "success": True}
    except ValueError as e:
        return {"error": str(e), "success": False}
    except Exception as e:
        log.error("remove_data_lineage_failed", from_fqn=from_fqn, to_fqn=to_fqn, error=str(e))
        return {"error": f"リネージ削除エラー: {e!s}", "success": False}
