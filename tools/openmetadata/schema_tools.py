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
        service_name: データベースサービス名 (例: "postgresql-prod")
        database_name: データベース名 (例: "dronedb")
        schema_name: スキーマ名 (例: "public")

    Returns:
        スキーマ情報の辞書。テーブル一覧・カラム情報を含む。
        存在しない場合は {"error": str, "success": False}
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
        return {"error": f"スキーマ取得エラー: {str(e)}", "success": False}


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

    Returns:
        {"tables": [{"fqn": str, "name": str, "description": str, "columns": int}], "success": bool}
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
        fqn: テーブルの完全修飾名 (例: "postgresql-prod.dronedb.public.customers")
        description: テーブルの説明（日本語可）
        tags: タグリスト (例: ["PII", "Customer"])
        owners: オーナーのメールアドレスリスト (例: ["team@example.com"])

    Returns:
        {"fqn": str, "updated": bool, "success": bool}
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
        return {"error": f"メタデータ登録エラー: {str(e)}", "success": False}


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

    Returns:
        {"table_fqn": str, "column": str, "updated": bool, "success": bool}
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
