"""
OpenMetadata Tool 統合テスト
実行前に OPENMETADATA_HOST と OPENMETADATA_JWT_TOKEN を設定してください。
"""
import pytest
from unittest.mock import MagicMock, patch
from tools.openmetadata.schema_tools import get_database_schema, list_tables, register_table_metadata
from tools.openmetadata.search_tools import search_data_assets
from tools.openmetadata.lineage_tools import get_data_lineage


@pytest.fixture
def mock_om_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(
        "tools.openmetadata.schema_tools.get_openmetadata_client",
        lambda: client
    )
    monkeypatch.setattr(
        "tools.openmetadata.search_tools.get_openmetadata_client",
        lambda: client
    )
    monkeypatch.setattr(
        "tools.openmetadata.lineage_tools.get_openmetadata_client",
        lambda: client
    )
    return client


class TestGetDatabaseSchema:
    def test_existing_schema(self, mock_om_client):
        mock_om_client.get_database_schema.return_value = {
            "fullyQualifiedName": "postgresql-prod.dronedb.public",
            "name": "public",
        }
        mock_om_client.list_tables.return_value = [
            {"fullyQualifiedName": "postgresql-prod.dronedb.public.customers", "name": "customers", "columns": []}
        ]

        result = get_database_schema.invoke({
            "service_name": "postgresql-prod",
            "database_name": "dronedb",
            "schema_name": "public",
        })

        assert result["success"] is True
        assert result["fqn"] == "postgresql-prod.dronedb.public"
        assert len(result["tables"]) == 1

    def test_not_found_schema(self, mock_om_client):
        mock_om_client.get_database_schema.return_value = None

        result = get_database_schema.invoke({
            "service_name": "postgresql-prod",
            "database_name": "dronedb",
            "schema_name": "nonexistent",
        })

        assert result["success"] is False
        assert "見つかりません" in result["error"]


class TestSearchDataAssets:
    def test_search_returns_results(self, mock_om_client):
        mock_om_client.search_assets.return_value = [
            {
                "fullyQualifiedName": "postgresql-prod.dronedb.public.customers",
                "name": "customers",
                "entityType": "table",
                "description": "顧客テーブル",
                "tags": [{"tagFQN": "PII"}],
            }
        ]

        result = search_data_assets.invoke({"query": "顧客", "asset_type": "table", "limit": 10})

        assert result["success"] is True
        assert result["total"] == 1
        assert result["assets"][0]["name"] == "customers"

    def test_search_empty_results(self, mock_om_client):
        mock_om_client.search_assets.return_value = []

        result = search_data_assets.invoke({"query": "存在しないデータ"})

        assert result["success"] is True
        assert result["total"] == 0


class TestRegisterTableMetadata:
    def test_register_success(self, mock_om_client):
        mock_om_client.patch_table.return_value = {
            "fullyQualifiedName": "postgresql-prod.dronedb.public.customers"
        }

        result = register_table_metadata.invoke({
            "fqn": "postgresql-prod.dronedb.public.customers",
            "description": "顧客マスタデータ",
            "tags": ["PII", "Customer"],
            "owners": ["team@example.com"],
        })

        assert result["success"] is True
        assert result["updated"] is True

    def test_register_not_found(self, mock_om_client):
        mock_om_client.patch_table.side_effect = ValueError("Table not found")

        result = register_table_metadata.invoke({
            "fqn": "postgresql-prod.dronedb.public.nonexistent",
            "description": "test",
            "tags": [],
            "owners": [],
        })

        assert result["success"] is False
