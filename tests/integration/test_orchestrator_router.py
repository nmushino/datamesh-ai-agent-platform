"""
Orchestrator 意図分類・ルーティングのテスト
"""
import pytest
from agent.orchestrator.router import classify_intent, route_to_agent


@pytest.mark.parametrize("text,expected_intent", [
    ("スキーマを同期してください",             "schema_sync"),
    ("テーブルをOpenMetadataに登録して",       "schema_sync"),
    ("顧客テーブルの説明を教えてください",     "metadata_search"),
    ("データを検索して",                       "metadata_search"),
    ("顧客を登録してください",                 "data_register"),
    ("BOMを登録したい",                        "data_register"),
    ("顧客情報を検索して",                     "data_search"),
    ("顧客情報を更新してください",             "data_update"),
    ("テーブルの説明を更新して",               "metadata_update"),
    ("データの流れを確認したい",               "lineage_check"),
    ("こんにちは",                             "chitchat"),
    ("よくわからない質問です",                 "unknown"),
])
def test_classify_intent(text, expected_intent):
    assert classify_intent(text) == expected_intent


@pytest.mark.parametrize("intent,expected_agent", [
    ("chitchat",         "chitchat"),
    ("schema_sync",      "schema"),
    ("metadata_search",  "search"),
    ("metadata_update",  "schema"),
    ("data_register",    "registration"),
    ("data_search",      "search"),
    ("data_update",      "registration"),
    ("lineage_check",    "search"),
    ("unknown",          "search"),
])
def test_route_to_agent(intent, expected_agent):
    state = {"intent": intent, "messages": [], "thread_id": "test"}
    assert route_to_agent(state) == expected_agent
