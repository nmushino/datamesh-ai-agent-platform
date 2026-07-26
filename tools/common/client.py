import json
import os
from functools import lru_cache
from typing import ClassVar
from urllib.parse import quote, quote_plus

import httpx
import structlog
from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    AuthProvider,
    OpenMetadataConnection,
)
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)
from metadata.ingestion.ometa.ometa_api import OpenMetadata

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
    _DATA_ASSET_ENTITY_TYPES: ClassVar[set[str]] = {"table", "topic", "pipeline", "dataProduct"}

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
        # NOTE: q=* だと更新頻度の高い tableColumn 等の非データ資産で埋まり、
        # limit*4 件取得しても実データ資産が limit 未満しか残らないことが
        # あった(実測: limit=5 で1件のみ)。entityType をクエリ自体で
        # 絞り込むことで、必要件数を確実に取得する。
        entity_types = " OR ".join(self._DATA_ASSET_ENTITY_TYPES)
        q = quote_plus(f"entityType:({entity_types})")
        response = self._client.client.get(
            f"/search/query?q={q}&index=all&size={limit}&deleted=false"
            "&sort_field=updatedAt&sort_order=desc"
        )
        hits = (response or {}).get("hits", {}).get("hits", [])
        return [hit.get("_source", {}) for hit in hits][:limit]

    def get_owned_assets(self, owner_name: str, limit: int = 10) -> list[dict]:
        # NOTE: OpenMetadata の「My Data」画面 (/users/{name}/mydata) は
        # ユーザーエンティティの owns フィールド(実際の所有関係)を表示する。
        # 以前は search/query の全文検索でowners配列内の名前一致を推測して
        # いたが、これは entityType の異なる無関係なエンティティ(ingestion
        # pipeline等)も混ざり、My Data 画面の実際の表示と食い違うことがある
        # ため、owns フィールドを直接使う方式に変更した。
        user = self._client.client.get(f"/users/name/{owner_name}?fields=owns")
        if not user:
            return []
        owns = user.get("owns") or []
        owned = [o for o in owns if o.get("type") in self._DATA_ASSET_ENTITY_TYPES]
        return owned[:limit]

    def create_or_update_table(self, request: dict) -> dict:
        from metadata.generated.schema.api.data.createTable import CreateTableRequest
        result = self._client.create_or_update(data=CreateTableRequest(**request))
        return result.dict()

    def create_or_update_topic(self, request: dict) -> dict:
        # NOTE: pydantic SDK (CreateTopicRequest) はデフォルト値の retentionSize を
        # 文字列 "-1" としてシリアライズしてしまい、サーバー(1.13.0)側の数値型
        # バリデーションに弾かれ "Invalid request format" になる。生の REST PUT を
        # 使えば同じペイロードで正常に作成できるため、SDK モデルを経由しない。
        result = self._client.client.put("/topics", data=json.dumps(request, ensure_ascii=False))
        if not result:
            raise ValueError("トピック作成に失敗しました(レスポンスが空)")
        return result

    def get_topic(self, fqn: str) -> dict | None:
        # NOTE: owners/tags/dataProducts/certification/messageSchema は全て
        # fields指定しないと返らない。PUT はエンティティ全体を置き換えるため、
        # 未指定フィールドを消さないよう、まず既存状態を取得してマージする用途で使う。
        # OMは404レスポンスに"code"フィールドを含めるため、REST clientの
        # _one_request() がこれを APIError として raise する(Noneを返さない)。
        # 新規トピック(まだ存在しない)の場合はここで raise されるのを吸収し、
        # None を返して create_or_update_topic 側の新規作成に進めるようにする。
        from metadata.ingestion.ometa.client import APIError
        try:
            return self._client.client.get(
                f"/topics/name/{quote(fqn)}"
                "?fields=owners,tags,dataProducts,domains,certification,messageSchema"
            )
        except APIError as e:
            if getattr(e, "code", None) == 404 or "not found" in str(e).lower():
                return None
            raise

    def get_team_id_by_name(self, team_name: str) -> str:
        # NOTE: quote_plus はスペースを "+" に変換するが、これはクエリ文字列用の
        # エンコーディングであり URL パスセグメントには使えない
        # ("Team B" が /teams/name/Team+B になり 404 になっていた)。
        # パスセグメントには quote (スペース -> %20) を使う。
        team = self._client.client.get(f"/teams/name/{quote(team_name)}")
        if not team:
            raise ValueError(f"チームが見つかりません: {team_name}")
        return team["id"]

    def get_data_product_domain_fqn(self, data_product_name: str) -> str | None:
        dp = self._client.client.get(
            f"/dataProducts/name/{quote(data_product_name)}?fields=domains"
        )
        if not dp:
            raise ValueError(f"データプロダクトが見つかりません: {data_product_name}")
        domains = dp.get("domains") or []
        return domains[0]["fullyQualifiedName"] if domains else None

    def upsert_topic_metadata(
        self,
        topic_name: str,
        service_name: str,
        description: str,
        partitions: int = 1,
        tags: list[str] | None = None,
        owner_teams: list[str] | None = None,
        tier: str | None = None,
        data_products: list[str] | None = None,
        schema_fields: list[dict] | None = None,
    ) -> dict:
        # NOTE: PUT /topics はエンティティ全体を置き換えるため、省略した
        # フィールド(owners/tags/dataProducts/messageSchema等)は既存の値が
        # あっても消える。既存トピックがあれば取得してベースにし、明示的に
        # 渡されたフィールドだけ上書きする。
        fqn = f"{service_name}.{topic_name}"
        existing = self.get_topic(fqn)

        request: dict = {
            "name": topic_name,
            "service": service_name,
            "description": description,
            "partitions": partitions,
        }

        if tags is not None or tier is not None:
            tag_fqns = list(tags or [])
            if tier is not None:
                tag_fqns.append(f"Tier.{tier}")
            request["tags"] = [{"tagFQN": t} for t in tag_fqns]
        elif existing and existing.get("tags"):
            request["tags"] = [{"tagFQN": t["tagFQN"]} for t in existing["tags"]]

        if owner_teams is not None:
            request["owners"] = [
                {"id": self.get_team_id_by_name(team), "type": "team"} for team in owner_teams
            ]
        elif existing and existing.get("owners"):
            request["owners"] = [{"id": o["id"], "type": o["type"]} for o in existing["owners"]]

        if data_products is not None:
            request["dataProducts"] = data_products
            # dataProducts のドメイン検証ルールに合わせ、対象トピックのドメインも
            # 明示的に一致させる必要がある(サービス継承ドメインだけでは不十分)。
            # data_products=[] (明示的に空リストで解除する場合)は data_products[0]
            # が IndexError になるため、非空の場合のみドメイン解決を行う。
            if data_products:
                domain_fqn = self.get_data_product_domain_fqn(data_products[0])
                if domain_fqn:
                    request["domains"] = [domain_fqn]
        elif existing and existing.get("dataProducts"):
            request["dataProducts"] = [dp["fullyQualifiedName"] for dp in existing["dataProducts"]]
            if existing.get("domains"):
                request["domains"] = [existing["domains"][0]["fullyQualifiedName"]]

        if schema_fields is not None:
            request["messageSchema"] = {
                "schemaText": (existing or {}).get("messageSchema", {}).get("schemaText", "{}"),
                "schemaType": (existing or {}).get("messageSchema", {}).get("schemaType", "Other"),
                "schemaFields": schema_fields,
            }
        elif existing and existing.get("messageSchema"):
            request["messageSchema"] = existing["messageSchema"]

        return self.create_or_update_topic(request)

    def set_topic_certification(self, topic_id: str, certification_tier: str | None) -> dict:
        if certification_tier is None:
            return {}
        patch = [{
            "op": "add",
            "path": "/certification",
            "value": {
                "tagLabel": {
                    "tagFQN": f"Certification.{certification_tier}",
                    "source": "Classification",
                    "labelType": "Manual",
                    "state": "Confirmed",
                }
            },
        }]
        result = self._client.client.patch(
            f"/topics/{topic_id}", data=json.dumps(patch, ensure_ascii=False)
        )
        if not result:
            raise ValueError("認証(Certification)の設定に失敗しました(レスポンスが空)")
        return result

    def create_or_update_glossary_term(self, request: dict) -> dict:
        # NOTE: create_or_update_topic と同様、SDK の CreateGlossaryTermRequest
        # モデルはサーバー(1.13.0)とのフィールド差分で拒否されることがあるため、
        # 生の REST PUT を使う。
        result = self._client.client.put("/glossaryTerms", data=json.dumps(request, ensure_ascii=False))
        if not result:
            raise ValueError("用語登録に失敗しました(レスポンスが空)")
        return result

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

    def get_all_quality_test_cases(self, limit: int = 200) -> list[dict]:
        # NOTE: /data-quality 画面のトップレベルサマリ(特定テーブルを指定しない
        # 全体集計)に相当するデータを返す。dataQuality/testSuites/executionSummary
        # は(未実行テストしかない状態では)全て0を返すため使えず、代わりに
        # 全テストケースを取得して自前で集計する。
        response = self._client.client.get(
            f"/dataQuality/testCases?fields=testCaseResult&limit={limit}"
        )
        return (response or {}).get("data", [])

    def get_topic_sample_data(self, topic_fqn: str, limit: int = 5) -> list[dict]:
        # NOTE: sampleData は /topics/name/{fqn} の fields クエリでは返らず、
        # id ベースの専用サブリソース /topics/{id}/sampleData でのみ取得できる。
        topic = self._client.client.get(f"/topics/name/{topic_fqn}")
        if not topic:
            raise ValueError(f"Topic not found: {topic_fqn}")
        response = self._client.client.get(f"/topics/{topic['id']}/sampleData")
        messages = ((response or {}).get("sampleData") or {}).get("messages") or []
        parsed = []
        for raw in messages[:limit]:
            try:
                parsed.append(json.loads(raw))
            except (TypeError, ValueError):
                parsed.append(raw)
        return parsed

    def create_test_case(self, test_case: dict) -> dict:
        from metadata.generated.schema.api.tests.createTestCase import (
            CreateTestCaseRequest,
        )
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
