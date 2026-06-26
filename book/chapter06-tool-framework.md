# Chapter 6: Tool Framework

## Tool 設計原則

1. **単一責務** — 1 Tool = 1 操作
2. **冪等性** — 同じ引数で何度呼んでも結果が変わらない
3. **明確な説明** — LLM が正しく使えるよう docstring を詳細に記述
4. **エラーハンドリング** — 失敗時は明確なエラーメッセージを返す

## OpenMetadata Tool 群

```python
# tools/openmetadata/schema_tools.py

@tool
def get_database_schema(
    service_name: str,
    database_name: str,
    schema_name: str
) -> dict:
    """
    OpenMetadata からデータベーススキーマ情報を取得します。

    Args:
        service_name: データベースサービス名 (例: "postgresql-prod")
        database_name: データベース名 (例: "dronedb")
        schema_name: スキーマ名 (例: "public")

    Returns:
        スキーマ情報の辞書 (テーブル一覧、カラム情報を含む)

    Raises:
        OpenMetadataNotFoundError: スキーマが存在しない場合
    """
    fqn = f"{service_name}.{database_name}.{schema_name}"
    return openmetadata_client.get_database_schema(fqn)


@tool
def search_data_assets(
    query: str,
    asset_type: str = "all",
    limit: int = 10
) -> list[dict]:
    """
    OpenMetadata のデータ資産を自然言語クエリで検索します。

    Args:
        query: 検索クエリ (例: "顧客の注文履歴")
        asset_type: 資産タイプ ("table", "topic", "pipeline", "all")
        limit: 最大取得件数

    Returns:
        マッチしたデータ資産のリスト
    """
    return openmetadata_client.search_assets(query, asset_type, limit)


@tool
def register_table_metadata(
    fqn: str,
    description: str,
    tags: list[str],
    owners: list[str]
) -> dict:
    """
    テーブルのメタデータ（説明・タグ・オーナー）を登録・更新します。

    Args:
        fqn: テーブルの完全修飾名 (例: "postgresql-prod.dronedb.public.orders")
        description: テーブルの説明
        tags: タグリスト (例: ["PII", "Customer"])
        owners: オーナーのメールアドレスリスト

    Returns:
        更新されたテーブルメタデータ
    """
    return openmetadata_client.patch_table(fqn, {
        "description": description,
        "tags": tags,
        "owners": owners,
    })


@tool
def get_data_lineage(fqn: str, depth: int = 3) -> dict:
    """
    データリネージ（データの流れ）を取得します。

    Args:
        fqn: 起点となるエンティティの完全修飾名
        depth: リネージの深さ

    Returns:
        リネージグラフ (上流・下流エンティティを含む)
    """
    return openmetadata_client.get_lineage(fqn, depth)
```

## Business Tool 群

```python
# tools/business/customer_tools.py

@tool
def register_customer(
    customer_id: str,
    name: str,
    email: str,
    metadata: dict = None
) -> dict:
    """
    Quarkus Business API を通じて顧客を登録します。
    登録後、OpenMetadata にもメタデータを同期します。

    Args:
        customer_id: 顧客 ID
        name: 顧客名
        email: メールアドレス
        metadata: 追加メタデータ (任意)

    Returns:
        登録された顧客情報
    """
    response = business_api_client.post("/api/v1/customers", {
        "customerId": customer_id,
        "name": name,
        "email": email,
        "metadata": metadata or {},
    })
    return response.json()


@tool
def search_customers(
    query: str,
    filters: dict = None
) -> list[dict]:
    """
    顧客データを検索します。

    Args:
        query: 検索クエリ
        filters: フィルタ条件 (例: {"status": "active"})

    Returns:
        マッチした顧客リスト
    """
    params = {"q": query, **(filters or {})}
    response = business_api_client.get("/api/v1/customers/search", params)
    return response.json()
```

## Tool 登録・管理

```python
# agent/common/tool_registry.py

OPENMETADATA_TOOLS = [
    get_database_schema,
    search_data_assets,
    register_table_metadata,
    get_data_lineage,
]

BUSINESS_TOOLS = [
    register_customer,
    search_customers,
    register_bom,
    search_inventory,
]

OPENSHIFT_TOOLS = [
    get_pod_status,
    scale_deployment,
    get_logs,
]

def get_tools_for_agent(agent_type: str) -> list:
    tool_map = {
        "schema": OPENMETADATA_TOOLS,
        "registration": OPENMETADATA_TOOLS + BUSINESS_TOOLS,
        "search": OPENMETADATA_TOOLS + BUSINESS_TOOLS,
        "operations": OPENSHIFT_TOOLS,
    }
    return tool_map.get(agent_type, [])
```
