import structlog
from langchain_core.tools import tool

from tools.common.client import get_openmetadata_client

log = structlog.get_logger()


@tool
def get_database_schema(
    service_name: str,
    database_name: str,
    schema_name: str,
) -> dict:
    """
    OpenMetadata からデータベーススキーマ情報を取得します。

    Args:
        service_name: データベースサービス名。実在の値が不明な場合は先に
            search_data_assets で検索して確認すること
            (例: "external-shop-cluster-postgres-asite:5432")
        database_name: データベース名 (例: "droneshopdb")
        schema_name: スキーマ名 (例: "droneshop")
    """
    fqn = f"{service_name}.{database_name}.{schema_name}"
    log.info("get_database_schema", fqn=fqn)
    try:
        client = get_openmetadata_client()
        schema = client.get_database_schema(fqn)
        if schema is None:
            return {"error": f"スキーマが見つかりません: {fqn}", "success": False}
        tables = client.list_tables(fqn)
        return {"fqn": fqn, "schema": schema, "tables": tables, "success": True}
    except Exception as e:
        log.error("get_database_schema_failed", fqn=fqn, error=str(e))
        return {"error": f"スキーマ取得エラー: {e!s}", "success": False}


@tool
def list_tables(
    service_name: str,
    database_name: str,
    schema_name: str,
) -> dict:
    """
    データベーススキーマ内のテーブル一覧を取得します。

    Args:
        service_name: データベースサービス名
        database_name: データベース名
        schema_name: スキーマ名
    """
    fqn = f"{service_name}.{database_name}.{schema_name}"
    try:
        client = get_openmetadata_client()
        tables = client.list_tables(fqn)
        simplified = [
            {
                "fqn": t.get("fullyQualifiedName", ""),
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "columns": len(t.get("columns", [])),
                "tags": [tag.get("tagFQN", "") for tag in t.get("tags", [])],
            }
            for t in tables
        ]
        return {"tables": simplified, "total": len(simplified), "success": True}
    except Exception as e:
        log.error("list_tables_failed", fqn=fqn, error=str(e))
        return {"error": str(e), "success": False}


@tool
def register_table_metadata(
    fqn: str,
    description: str,
    tags: list[str],
    owners: list[str],
) -> dict:
    """
    テーブルのメタデータ（説明・タグ・オーナー）を登録・更新します。
    テーブルが存在しない場合はエラーを返します。

    Args:
        fqn: テーブルの完全修飾名。実在の値が不明な場合は先に
            search_data_assets で検索して確認すること
            (例: "external-shop-cluster-postgres-asite:5432.droneshopdb.droneshop.orders")
        description: テーブルの説明（日本語可）
        tags: タグリスト (例: ["PII", "Customer"])
        owners: オーナーのメールアドレスリスト (例: ["team@example.com"])
    """
    log.info("register_table_metadata", fqn=fqn, tags=tags)
    try:
        client = get_openmetadata_client()
        patch = {
            "description": description,
            "tags": [{"tagFQN": tag} for tag in tags],
            "owners": [{"name": owner, "type": "team"} for owner in owners],
        }
        result = client.patch_table(fqn, patch)
        return {"fqn": fqn, "updated": True, "result": result, "success": True}
    except ValueError as e:
        return {"error": str(e), "success": False}
    except Exception as e:
        log.error("register_table_metadata_failed", fqn=fqn, error=str(e))
        return {"error": f"メタデータ登録エラー: {e!s}", "success": False}


@tool
def register_topic_metadata(
    topic_name: str,
    service_name: str,
    description: str,
    partitions: int = 1,
    tags: list[str] | None = None,
) -> dict:
    """
    新しい Kafka トピックのメタデータを OpenMetadata に登録します。
    (OpenMetadata はメタデータ管理のみを行うため、実際の Kafka ブローカー上に
    トピックを作成するわけではない。既にブローカー側に存在するトピック、
    または将来作成予定のトピックについて、OpenMetadata 上での説明・所在を
    登録するためのツール)

    Args:
        topic_name: 登録するトピック名 (例: "oder-test")
        service_name: 対象サイトの Messaging Service 名。
            Aサイト: "external-shop-cluster-kafka-asite:9094"
            Bサイト: "external-shop-cluster-kafka-bsite:9094"
            Cサイト: "external-shop-cluster-kafka-csite:9094"
        description: トピックの説明（日本語可）
        partitions: パーティション数 (デフォルト1)
        tags: タグリスト (任意)
    """
    log.info("register_topic_metadata", topic_name=topic_name, service_name=service_name)
    try:
        client = get_openmetadata_client()
        request = {
            "name": topic_name,
            "service": service_name,
            "description": description,
            "partitions": partitions,
            "tags": [{"tagFQN": tag} for tag in (tags or [])],
        }
        result = client.create_or_update_topic(request)
        fqn = result.get("fullyQualifiedName", f"{service_name}.{topic_name}")
        return {"fqn": fqn, "created": True, "result": result, "success": True}
    except Exception as e:
        log.error("register_topic_metadata_failed", topic_name=topic_name, error=str(e))
        return {"error": f"トピック登録エラー: {e!s}", "success": False}


@tool
def register_glossary_term(
    term_name: str,
    description: str,
    glossary_name: str = "QuarkusDroneShopGlossary",
) -> dict:
    """
    新しいビジネス用語を OpenMetadata の用語集(Glossary)に登録します。
    新しいテーブル・トピックの調査中に、既存の用語集に無いドメイン固有の
    用語(例: 新しい業務イベント名)が見つかった場合に使う。

    Args:
        term_name: 用語名 (例: "OrderInEvent")
        description: 用語の説明（日本語可）
        glossary_name: 登録先の用語集名 (デフォルトはこの環境の唯一の用語集)
    """
    log.info("register_glossary_term", term_name=term_name, glossary_name=glossary_name)
    try:
        client = get_openmetadata_client()
        request = {
            "name": term_name,
            "description": description,
            "glossary": glossary_name,
        }
        result = client.create_or_update_glossary_term(request)
        return {"term": term_name, "fqn": result.get("fullyQualifiedName", ""), "created": True, "success": True}
    except Exception as e:
        log.error("register_glossary_term_failed", term_name=term_name, error=str(e))
        return {"error": f"用語登録エラー: {e!s}", "success": False}


@tool
def update_column_description(
    table_fqn: str,
    column_name: str,
    description: str,
    tags: list[str] | None = None,
) -> dict:
    """
    テーブルの特定カラムの説明・タグを更新します。

    Args:
        table_fqn: テーブルの完全修飾名
        column_name: カラム名
        description: カラムの説明
        tags: タグリスト (任意)
    """
    log.info("update_column_description", table_fqn=table_fqn, column=column_name)
    try:
        client = get_openmetadata_client()
        patch = {
            "columns": [{
                "name": column_name,
                "description": description,
                "tags": [{"tagFQN": t} for t in (tags or [])],
            }]
        }
        client.patch_table(table_fqn, patch)
        return {"table_fqn": table_fqn, "column": column_name, "updated": True, "success": True}
    except Exception as e:
        log.error("update_column_description_failed", error=str(e))
        return {"error": str(e), "success": False}
