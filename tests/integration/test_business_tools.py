"""
Business Tool 統合テスト（Quarkus API のモックを使用）
"""
from unittest.mock import MagicMock

import httpx
import pytest

from tools.business.customer_tools import register_customer, search_customers


@pytest.fixture
def mock_api_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(
        "tools.business.customer_tools.get_business_api_client",
        lambda: client
    )
    return client


class TestRegisterCustomer:
    def test_register_success(self, mock_api_client):
        mock_api_client.post.return_value = {
            "customerId": "CUST-ABCD1234",
            "name": "山田太郎",
            "email": "yamada@example.com",
            "status": "active",
        }

        result = register_customer.invoke({
            "customer_id": "CUST-ABCD1234",
            "name": "山田太郎",
            "email": "yamada@example.com",
        })

        assert result["success"] is True
        assert result["customerId"] == "CUST-ABCD1234"

    def test_register_duplicate(self, mock_api_client):
        response_mock = MagicMock()
        response_mock.status_code = 409
        response_mock.json.return_value = {"message": "Customer ID already exists"}
        mock_api_client.post.side_effect = httpx.HTTPStatusError(
            "Conflict", request=MagicMock(), response=response_mock
        )

        result = register_customer.invoke({
            "customer_id": "CUST-ABCD1234",
            "name": "山田太郎",
            "email": "yamada@example.com",
        })

        assert result["success"] is False
        assert "既に存在します" in result["error"]

    def test_register_api_unavailable(self, mock_api_client):
        mock_api_client.post.side_effect = httpx.RequestError("Connection refused", request=MagicMock())

        result = register_customer.invoke({
            "customer_id": "CUST-ABCD1234",
            "name": "山田太郎",
            "email": "yamada@example.com",
        })

        assert result["success"] is False
        assert "接続できません" in result["error"]


class TestSearchCustomers:
    def test_search_returns_results(self, mock_api_client):
        mock_api_client.get.return_value = {
            "customers": [
                {"customerId": "CUST-ABCD1234", "name": "山田太郎", "email": "yamada@example.com"}
            ],
            "total": 1,
        }

        result = search_customers.invoke({"query": "山田"})

        assert result["success"] is True
        assert result["total"] == 1
