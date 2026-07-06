import os
import httpx
import structlog
from functools import lru_cache
from urllib.parse import quote_plus

from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    OpenMetadataConnection,
    AuthProvider,
)
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)

log = structlog.get_logger()


class OpenMetadataClientWrapper:
    def __init__(self, host: str, jwt_token: str):
        server_config = OpenMetadataConnection(
            hostPort=host,
            authProvider=AuthProvider.openmetadata,
            securityConfig=OpenMetadataJWTClientConfig(jwtToken=jwt_token),
            # NOTE: このクライアントSDK (openmetadata-ingestion 1.3.0) は pydantic v1
            # 互換のため langchain 0.2.x と合わせて意図的に古いバージョンを使っている。
            # サーバーは 1.13.0 のため validate_versions() のメジャー/マイナー一致
            # チェックに引っかかるが、REST API 自体には後方互換性があるため無効化する。
            enableVersionValidation=False,
        )
        self._client = OpenMetadata(server_config)

    def get_table(self, fqn: str) -> dict | None:
        from metadata.generated.schema.entity.data.table import Table
        entity = self._client.get_by_name(entity=Table, fqn=fqn)
        return entity.dict() if entity else None

    def get_database_schema(self, fqn: str) -> dict | None:
        from metadata.generated.schema.entity.data.databaseSchema import DatabaseSchema
        entity = self._client.get_by_name(entity=DatabaseSchema, fqn=fqn)
        return entity.dict() if entity else None

    def list_tables(self, database_schema: str) -> list[dict]:
        from metadata.generated.schema.entity.data.table import Table
        tables = self._client.list_all_entities(
            entity=Table,
            params={"databaseSchema": database_schema},
        )
        return [t.dict() for t in tables]

    # NOTE: index="all" にはテーブル/トピック/データプロダクトのような実データ資産
    # 以外に、Kafkaブローカー自体(messagingService)や、データベース接続情報
    # (databaseService/database/databaseSchema)、品質テスト定義(testCase)なども
    # 含まれる。これらが limit 件数の枠を消費し、実データ資産(特にテーブル)が
    # 押し出されて表示されなくなる事象があったため、"all" 検索時はクライアント側で
    # 除外する。
    _DATA_ASSET_ENTITY_TYPES = {"table", "topic", "pipeline", "dataProduct"}

    def search_assets(self, query: str, asset_type: str = "all", limit: int = 10) -> list[dict]:
        # es_search_from_fqn requires an actual entity class (e.g. Table) since it keys
        # ES_INDEX_MAP by entity_type.__name__, so it can't express a cross-type "all"
        # search. Call the raw OpenMetadata search API directly instead.
        index_map = {
            "table":        "table_search_index",
            "topic":        "topic_search_index",
            "pipeline":     "pipeline_search_index",
            "data_product": "data_product_search_index",
            "all":          "all",
        }
        index = index_map.get(asset_type, "all")
        q = quote_plus(query) if query else "*"
        # "all" はブローカー/DB接続情報/テストケース等で埋まりやすいため、
        # 除外後になお limit 件数を確保できるよう多めに取得してから絞り込む。
        fetch_size = limit * 4 if index == "all" else limit
        response = self._client.client.get(
            f"/search/query?q={q}&index={index}&size={fetch_size}&deleted=false"
        )
        hits = (response or {}).get("hits", {}).get("hits", [])
        sources = [hit.get("_source", {}) for hit in hits]
        if index == "all":
            sources = [s for s in sources if s.get("entityType") in self._DATA_ASSET_ENTITY_TYPES]
        return sources[:limit]

    def get_recent_activity(self, limit: int = 10) -> list[dict]:
        response = self._client.client.get(
            f"/search/query?q=*&index=all&size={limit * 4}&deleted=false"
            "&sort_field=updatedAt&sort_order=desc"
        )
        hits = (response or {}).get("hits", {}).get("hits", [])
        sources = [hit.get("_source", {}) for hit in hits]
        sources = [s for s in sources if s.get("entityType") in self._DATA_ASSET_ENTITY_TYPES]
        return sources[:limit]

    def get_owned_assets(self, owner_name: str, limit: int = 10) -> list[dict]:
        # NOTE: owners.name などのフィールド指定クエリはこの ES マッピングでは
        # 0 件になる (nested/keyword フィールドの扱いの都合と思われる)。
        # ワイルドカードの全文検索であれば owners 内の name/displayName に
        # ヒットすることを確認済みのため、こちらを使う。
        q = quote_plus(f"*{owner_name}*")
        response = self._client.client.get(
            f"/search/query?q={q}&index=all&size={limit * 4}&deleted=false"
        )
        hits = (response or {}).get("hits", {}).get("hits", [])
        owned = [
            hit.get("_source", {})
            for hit in hits
            if hit.get("_source", {}).get("entityType") in self._DATA_ASSET_ENTITY_TYPES
            and any(
                o.get("name") == owner_name or o.get("displayName") == owner_name
                for o in (hit.get("_source", {}).get("owners") or [])
            )
        ]
        return owned[:limit]

    def create_or_update_table(self, request: dict) -> dict:
        from metadata.generated.schema.api.data.createTable import CreateTableRequest
        result = self._client.create_or_update(data=CreateTableRequest(**request))
        return result.dict()

    def patch_table(self, fqn: str, patch: dict) -> dict:
        from metadata.generated.schema.entity.data.table import Table
        table = self._client.get_by_name(entity=Table, fqn=fqn)
        if not table:
            raise ValueError(f"Table not found: {fqn}")
        updated = self._client.patch(entity=Table, source=table, dest_dict=patch)
        return updated.dict()

    def get_lineage(self, fqn: str, entity_type: str = "table", depth: int = 3) -> dict:
        # NOTE: get_by_name() 経由の pydantic SDK モデルはサーバー(1.13.0)との
        # スキーマ差分で ValidationError になるため、生の REST API を使う。
        response = self._client.client.get(
            f"/lineage/{entity_type}/name/{fqn}?upstreamDepth={depth}&downstreamDepth={depth}"
        )
        if not response or not response.get("entity"):
            raise ValueError(f"Entity not found: {fqn}")
        return response

    def get_quality_test_cases(self, table_fqn: str, limit: int = 20) -> list[dict]:
        # NOTE: get_table() 経由の pydantic SDK モデルはサーバー(1.13.0)とSDK(1.3.0)の
        # スキーマ差分で ValidationError になり使えないため、生の REST API を叩く。
        # /data-quality 画面が表示するのと同じ、テーブルに紐づくテストケース定義と
        # 直近の実行結果(testCaseResult)を返す。
        entity_link = quote_plus(f"<#E::table::{table_fqn}>")
        response = self._client.client.get(
            f"/dataQuality/testCases/search/list"
            f"?entityLink={entity_link}&fields=testCaseResult&limit={limit}"
        )
        return (response or {}).get("data", [])

    def create_test_case(self, test_case: dict) -> dict:
        from metadata.generated.schema.api.tests.createTestCase import CreateTestCaseRequest
        result = self._client.create_or_update(data=CreateTestCaseRequest(**test_case))
        return result.dict()


class BusinessApiClient:
    def __init__(self, base_url: str, token: str | None = None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=10.0,
        )

    def get(self, path: str, params: dict | None = None) -> dict:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, json: dict) -> dict:
        response = self._client.post(path, json=json)
        response.raise_for_status()
        return response.json()

    def put(self, path: str, json: dict) -> dict:
        response = self._client.put(path, json=json)
        response.raise_for_status()
        return response.json()

    def patch(self, path: str, json: dict) -> dict:
        response = self._client.patch(path, json=json)
        response.raise_for_status()
        return response.json()


@lru_cache(maxsize=1)
def get_openmetadata_client() -> OpenMetadataClientWrapper:
    return OpenMetadataClientWrapper(
        host=os.environ["OPENMETADATA_HOST"],
        jwt_token=os.environ["OPENMETADATA_JWT_TOKEN"],
    )


@lru_cache(maxsize=1)
def get_business_api_client() -> BusinessApiClient:
    return BusinessApiClient(
        base_url=os.environ["BUSINESS_API_URL"],
        token=os.getenv("BUSINESS_API_TOKEN"),
    )
