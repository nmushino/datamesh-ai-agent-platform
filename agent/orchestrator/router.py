import re
from agent.common.state import AgentState

# キーワードベースの意図分類
_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    # NOTE: 挨拶・雑談は最優先でチェックする。LLM の判断 (tool_choice="auto") に
    # 任せると、指示に従わずツールを呼び出してしまうことがあり応答が遅くなる
    # (ReAct ループが発生し vLLM への往復が増える) ため、キーワードで確実に
    # 弾いてツール無しの chitchat_node に固定でルーティングする。
    ("chitchat", [
        r"^こんにちは[!!。、\s]*$", r"^こんばんは[!!。、\s]*$", r"^おはよう(ございます)?[!!。、\s]*$",
        r"^hello[!.\s]*$", r"^hi[!.\s]*$", r"^hey[!.\s]*$",
        r"^ありがとう(ございます)?[!!。、\s]*$", r"^よろしく(お願いします)?[!!。、\s]*$",
    ]),
    # NOTE: metadata_search の "検索"/"テーブル.*説明" 等は汎用的すぎるため、
    # より具体的な data_search / metadata_update / data_register / data_update
    # を先にチェックしないと誤って metadata_search にマッチしてしまう。
    ("schema_sync", [
        "スキーマ.*同期", "スキーマ.*登録", "スキーマ.*反映",
        "openmetadata.*登録", "テーブル.*登録", "schema.*sync",
        "トピック.*登録", "トピック.*追加", "トピック.*作成", "トピック.*削除",
        "topic.*register", "topic.*create", "topic.*delete",
        # NOTE: 実際のトピック名自体が英語("orders-topic"等)であることが多く、
        # 「orders-topicを削除して」のように英語のトピック名+日本語の動詞が
        # 混在するケースがある。この場合「トピック」というカタカナ語も
        # 「delete」という英語動詞も現れないため、上記のパターンだけでは
        # 一致しない。"topic" という文字列(英語トピック名の一部としても
        # 頻出)と日本語の動詞を組み合わせて拾う。
        "topic.*作成", "topic.*追加", "topic.*登録", "topic.*削除",
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
        "検索.*顧客",
    ]),
    ("data_update", [
        "顧客.*更新", "情報.*変更", "ステータス.*変更",
        "update.*customer",
    ]),
    ("metadata_search", [
        "テーブル.*説明", "データ.*探", "どこ.*ある", "検索",
        "メタデータ", "説明.*教えて", "lineage", "リネージ",
        "品質.*確認", "品質.*スコア", "search",
        "データ資産", "資産.*一覧", "資産.*リスト", "データ.*一覧",
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
    "chitchat":         "chitchat",
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


def classify_intent_detailed(text: str) -> tuple[str, str | None]:
    """意図と、判定の根拠になった正規表現パターンの組を返す。
    ステータス表示で「なぜその意図と判定したか」を示すために使う。"""
    text_lower = text.lower()
    for intent, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent, pattern
    return "unknown", None


def classify_intent(text: str) -> str:
    intent, _matched_pattern = classify_intent_detailed(text)
    return intent


def route_to_agent(state: AgentState) -> str:
    intent = state.get("intent", "unknown")
    return _INTENT_TO_AGENT.get(intent, "search")
