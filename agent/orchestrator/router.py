import re
from agent.common.state import AgentState

# キーワードベースの意図分類
_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("schema_sync", [
        "スキーマ.*同期", "スキーマ.*登録", "スキーマ.*反映",
        "openmetadata.*登録", "テーブル.*登録", "schema.*sync",
    ]),
    ("metadata_search", [
        "テーブル.*説明", "データ.*探", "どこ.*ある", "検索",
        "メタデータ", "説明.*教えて", "lineage", "リネージ",
        "品質.*確認", "品質.*スコア", "search",
        "データ資産", "資産.*一覧", "資産.*リスト", "データ.*一覧",
    ]),
    ("metadata_update", [
        "説明.*更新", "タグ.*付け", "オーナー.*変更",
        "description.*変更", "メタデータ.*更新",
    ]),
    ("data_register", [
        "顧客.*登録", "bom.*登録", "データ.*追加", "新規.*登録",
        "register.*customer", "register.*bom",
    ]),
    ("data_search", [
        "顧客.*検索", "顧客.*探", "bom.*検索", "bom.*探",
        "顧客.*教えて", "検索.*顧客",
    ]),
    ("data_update", [
        "顧客.*更新", "情報.*変更", "ステータス.*変更",
        "update.*customer",
    ]),
    ("lineage_check", [
        "データの流れ", "上流", "下流", "lineage", "リネージ",
    ]),
    # Platform Ops — OpenShift / Git / Filesystem 操作
    ("platform_ops", [
        "pod.*確認", "pod.*ログ", "デプロイ.*状態", "再起動",
        "スケール", "レプリカ", "クラスター",
        "oc get", "kubectl", "deployment.*確認",
        "ソース.*検索", "git.*ブランチ", "コミット",
        "ファイル.*読", "ファイル.*検索",
        "logs?", "restart", "scale",
    ]),
]

_INTENT_TO_AGENT = {
    "schema_sync":      "schema",
    "metadata_search":  "search",
    "metadata_update":  "schema",
    "data_register":    "registration",
    "data_search":      "search",
    "data_update":      "registration",
    "lineage_check":    "search",
    "platform_ops":     "platform_ops",
    "unknown":          "search",
}


def classify_intent(text: str) -> str:
    text_lower = text.lower()
    for intent, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent
    return "unknown"


def route_to_agent(state: AgentState) -> str:
    intent = state.get("intent", "unknown")
    return _INTENT_TO_AGENT.get(intent, "search")
