import contextvars
import json
import re
import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END

from agent.common.state import AgentState
from agent.common.llm import get_llm, sum_tokens
from agent.orchestrator.router import classify_intent_detailed, route_to_agent
from agent.schema_agent.agent import SCHEMA_TOOLS, SYSTEM_PROMPT as SCHEMA_SYSTEM_PROMPT
from agent.search_agent.agent import SEARCH_TOOLS, SYSTEM_PROMPT as SEARCH_SYSTEM_PROMPT
from agent.registration_agent.agent import REGISTRATION_TOOLS, SYSTEM_PROMPT as REGISTRATION_SYSTEM_PROMPT

log = structlog.get_logger()

# NOTE: 以前は langgraph.prebuilt.create_react_agent (内部でさらに1段コンパイル済み
# StateGraphを持つ) をサブエージェントとして使い、外側の create_graph() のノードの
# 中から .stream()/.invoke() していた。しかし外側グラフの実行(Pregel)経由でこの
# 入れ子のグラフを呼び出すと、vLLM側は正常に応答を生成しているにもかかわらず
# 最終メッセージが空になる現象が再現性高く発生した(素のPython関数として直接
# 呼び出した場合は問題なし。エージェントキャッシュ・LLMクライアントキャッシュ・
# config分離のいずれも原因ではなく、ネストしたグラフ実行そのものが原因と判明)。
# そのため、サブエージェントは create_react_agent を使わず、ツールバインディング
# された LLM を手動でループさせる形に変更し、ネストしたグラフ実行を避ける。
_SUBAGENT_CONFIGS = {
    "schema":       (SCHEMA_TOOLS, SCHEMA_SYSTEM_PROMPT),
    "search":       (SEARCH_TOOLS, SEARCH_SYSTEM_PROMPT),
    "registration": (REGISTRATION_TOOLS, REGISTRATION_SYSTEM_PROMPT),
}


# NOTE: AgentState["messages"] は Annotated[list, operator.add] で
# チェックポインタ経由で会話全体を蓄積し続けるため、長い会話では
# vLLM の max-model-len (8192) を超えて 400 エラーになる。LLM へ渡す
# 直前には必ず直近 N 件(HumanMessageと最終回答のAIMessageのみ。ツール
# 呼び出し過程は _recent_messages 側で除外する)だけに絞ること。
RECENT_MESSAGES_LIMIT = 4

# 過去の「最終回答」自体が大きなMarkdownテーブルであることが多く(一覧系の
# 依頼が中心のため)、ツール呼び出し過程を除いても複数件残すだけで
# 肥大化することが確認された。直近1件以外の過去のAIMessageは参考情報
# として短く切り詰める。
OLD_ANSWER_MAX_CHARS = 150


def _recent_messages(state: AgentState) -> list:
    messages = state["messages"]
    # 過去のターンのツール呼び出し過程(tool_callsを持つAIMessageとその
    # ToolMessage)は、そのターンの回答を生成した時点で役目を終えており、
    # 将来のターンの会話継続には不要なため、履歴からは除外する
    # (1ターンにつき Human, AIMessage(tool_call), ToolMessage, 最終AIMessage の
    # 最大4件が積み上がり、これをそのまま残すとすぐにコンテキストが
    # 肥大化してしまうため)。HumanMessageと最終回答のAIMessageだけを残す。
    filtered = [
        m for m in messages
        if not isinstance(m, ToolMessage) and not (isinstance(m, AIMessage) and getattr(m, "tool_calls", None))
    ]
    recent = filtered[-RECENT_MESSAGES_LIMIT:] if len(filtered) > RECENT_MESSAGES_LIMIT else filtered
    trimmed = []
    for i, m in enumerate(recent):
        is_last = i == len(recent) - 1
        if isinstance(m, AIMessage) and not is_last and len(str(m.content)) > OLD_ANSWER_MAX_CHARS:
            m = AIMessage(content=str(m.content)[:OLD_ANSWER_MAX_CHARS] + "...(省略)")
        trimmed.append(m)
    return trimmed


# NOTE: config["configurable"] 経由で status キューを渡そうとしたが、
# PostgresSaver チェックポインタ付きでコンパイルしたグラフでは
# configurable がチェックポインタの識別キー以外を除去してしまい、
# ノード関数まで届かないことが判明した (contextvars ならスレッド内の
# 呼び出しスタックに伝播するため、チェックポインタの介在を受けない)。
_status_queue_var: contextvars.ContextVar = contextvars.ContextVar(
    "status_queue", default=None
)

# ツール名 -> 検索中表示用の日本語ラベル (「意図を判定しています」だけでは
# 何をしているか分からないという要望を受け、サブエージェント内のツール
# 呼び出し単位でも status キューへ通知する)
_TOOL_STATUS_LABELS = {
    "search_data_assets":     "OpenMetadata でデータ資産を検索しています...",
    "get_recent_activity":    "OpenMetadata の最近の更新をクロールしています...",
    "get_my_data_assets":     "OpenMetadata でオーナー別データを検索しています...",
    "get_topic_sample_data":  "Kafkaトピックのサンプルデータを取得しています...",
    "get_database_schema":    "テーブルのスキーマ情報を取得しています...",
    "list_tables":            "テーブル一覧を取得しています...",
    "register_table_metadata": "テーブルメタデータを登録しています...",
    "register_topic_metadata": "Kafkaトピックのメタデータを登録しています...",
    "create_kafka_topic":     "対象サイトの実ブローカーにトピックを作成しています...",
    "update_column_description": "カラムの説明を更新しています...",
    "get_data_lineage":       "データリネージを辿っています...",
    "get_quality_metrics":    "データ品質メトリクスを取得しています...",
    "create_quality_rule":    "データ品質ルールを作成しています...",
    "search_customers":       "顧客情報を検索しています...",
    "search_bom":             "BOM情報を検索しています...",
}


_MAX_TOOL_ITERATIONS = 5

TRUNCATION_NOTICE = (
    "\n\n⚠️ 応答が長いため、規定回数の自動継続後もまだ途中です。"
    "チャット設定の応答の長さを「中」以上に変更して、もう一度お試しください。"
)

# 応答が max_tokens で切れた場合に自動で「続き」を生成させる最大回数。
# 1回で終わらせず何度でも切り出して結合してほしいという要望に対応する。
_MAX_CONTINUATIONS = 4


def _continue_if_truncated(llm, messages: list, ai_message: AIMessage, status_q=None) -> AIMessage:
    """LLMの応答が max_tokens に達して途中で切れた場合(finish_reason == "length")、
    「続きを出力してください」と自動で追加リクエストし、切れなくなるか
    _MAX_CONTINUATIONS 回に達するまで繰り返して結合する。"""
    full_content = str(ai_message.content)
    working_messages = list(messages) + [ai_message]
    continuations = 0
    while (ai_message.response_metadata or {}).get("finish_reason") == "length" and continuations < _MAX_CONTINUATIONS:
        if status_q:
            status_q.put(f"応答が長いため続きを生成しています... ({continuations + 1}/{_MAX_CONTINUATIONS})")
        working_messages.append(
            HumanMessage(content=(
                "直前のあなたの発言は表の行の途中で切れています。その最後の行を"
                "先頭から書き直し、正しく完成させたうえで、続きの行を同じ表の"
                "フォーマット(| 列 | 列 |)で追加していってください。見出し(###)や"
                "表のヘッダー行・区切り線(| --- | --- |)は再度出力しないこと。"
                "新しい表を始めないこと。"
            ))
        )
        ai_message = llm.invoke(working_messages)
        # NOTE: モデルは「切れた最後の行」を先頭から書き直す挙動をするため、
        # こちらの蓄積側でもその未完成な最後の行を切り捨ててから継続分を
        # 連結する(そのまま連結すると同じ行が重複してしまう)。
        prior_lines = full_content.rstrip("\n").split("\n")
        full_content = "\n".join(prior_lines[:-1]) if len(prior_lines) > 1 else ""
        full_content += ("\n" if full_content else "") + str(ai_message.content)
        working_messages.append(ai_message)
        continuations += 1
    if (ai_message.response_metadata or {}).get("finish_reason") == "length":
        full_content += TRUNCATION_NOTICE
    return AIMessage(content=full_content)


_SITE_KEYWORD_TO_FQN_PART = {"Aサイト": "asite", "Bサイト": "bsite", "Cサイト": "csite"}

_NAME_FRAGMENT_RE = re.compile(r"[A-Za-z]{3,}")


def _extract_name_fragment(text: str) -> str:
    """検索クエリ文字列から英字のみの断片を抜き出し、サイト絞り込みと
    組み合わせるための緩いワイルドカードとして使う(例: "Order-in" -> "order")。
    元のクエリを完全に捨てて limit を大きくする方式では、該当サイトの
    全トピックの詳細説明が丸ごとコンテキストに載ってしまいプロンプトが
    肥大化する(実測: 6706トークンまで増加しコンテキスト長超過を誘発)ため、
    可能な限りこちらでトピック名まで絞り込む。"""
    m = _NAME_FRAGMENT_RE.search(text)
    return m.group(0).lower() if m else ""


def _normalize_site_query(tool_name: str, args: dict, user_text: str = "") -> dict:
    """search_data_assets の query に「Aサイト」等の日本語がそのまま
    残っている場合、FQN ワイルドカードクエリに強制的に書き換える。
    プロンプトでの指示だけでは徹底されないことがあり(他サイトの複製先
    説明にも一致してしまい、結果が肥大化してコンテキスト長を超える
    原因になっていた)、確実性のためコード側でも補正する。"""
    if tool_name != "search_data_assets":
        return args
    query = args.get("query", "")
    if "fullyQualifiedName:" in query:
        return args
    for keyword, fqn_part in _SITE_KEYWORD_TO_FQN_PART.items():
        if keyword in query:
            new_args = dict(args)
            new_args["query"] = f"fullyQualifiedName:*{fqn_part}*"
            log.warning("site_query_normalized", original_query=query, new_query=new_args["query"])
            return new_args
    # NOTE: サンプルデータ取得のように「まずトピック名だけで検索して FQN を
    # 特定してから別ツールを呼ぶ」流れでは、モデルが検索クエリ自体には
    # サイト名を含めないことがある(例: ユーザーが「Aサイトの Order-in
    # トピック」と言っても query="Order-in" だけを渡す)。この場合、元の
    # ユーザー発言にサイト指定があれば、そちらを優先してサイト絞り込みの
    # ワイルドカードクエリに書き換える(元のトピック名指定は捨てて良い。
    # asset_type と limit 拡大で該当サイトの全件から選ばせる)。
    for keyword, fqn_part in _SITE_KEYWORD_TO_FQN_PART.items():
        if keyword in user_text:
            fragment = _extract_name_fragment(query)
            new_args = dict(args)
            new_args["query"] = (
                f"fullyQualifiedName:*{fqn_part}*{fragment}*" if fragment
                else f"fullyQualifiedName:*{fqn_part}*"
            )
            if not fragment:
                new_args["limit"] = max(int(args.get("limit", 10)), 20)
            log.warning(
                "site_query_normalized_from_context",
                original_query=query, new_query=new_args["query"], user_text=user_text,
            )
            return new_args
    return args


# NOTE: 実際の外部ブローカーへの書き込みを伴うツールはプロンプト指示だけでは
# 「先に確認を求める」を徹底できない(検証済み: 依頼された直後の1ターン目で
# そのまま実行しようとした)ため、コード側で「直前の会話で既に承認確認を
# 提示済みかどうか」を判定し、未確認ならツール自体を実行させずに確認メッセージ
# だけを返す安全策を設ける。
_CONFIRM_BEFORE_EXECUTE_TOOLS = {"create_kafka_topic"}


def _confirmation_pending_message(tc_args: dict) -> AIMessage:
    topic = tc_args.get("topic_name", "")
    service = tc_args.get("service_name", "")
    return AIMessage(content=(
        f"{service} の実ブローカーに `{topic}` トピックを新規作成します。"
        f"この操作は外部システムへの実際の書き込みを伴うため、承認が必要です。"
        f"よろしければ「承認します」のように返信してください。"
    ))


def _already_confirmed(topic_name: str, prior_messages: list) -> bool:
    if not topic_name:
        return False
    return any(
        isinstance(m, AIMessage) and "承認" in str(m.content) and topic_name in str(m.content)
        for m in prior_messages
    )


def _topic_already_created_on_broker(topic_name: str, service_name: str, prior_messages: list) -> bool:
    for m in prior_messages:
        if isinstance(m, ToolMessage) and m.name == "create_kafka_topic":
            try:
                data = json.loads(m.content)
            except (TypeError, ValueError):
                continue
            if data.get("success") and data.get("topic_name") == topic_name and data.get("service_name") == service_name:
                return True
    return False


def _inject_missing_topic_creation(tool_calls: list, prior_messages: list) -> list:
    """register_topic_metadata が呼ばれたが、対応する create_kafka_topic が
    まだ成功していない場合、モデルが手順を省略しても実ブローカーへの作成を
    飛ばさないよう、直前に create_kafka_topic 呼び出しを自動的に挿入する。"""
    result = []
    for tc in tool_calls:
        if tc["name"] == "register_topic_metadata":
            topic_name = tc["args"].get("topic_name", "")
            service_name = tc["args"].get("service_name", "")
            if not _topic_already_created_on_broker(topic_name, service_name, prior_messages):
                result.append({
                    "name": "create_kafka_topic",
                    "args": {
                        "topic_name": topic_name,
                        "service_name": service_name,
                        "partitions": tc["args"].get("partitions", 1),
                    },
                    "id": f"{tc['id']}-auto-create",
                    "type": "tool_call",
                })
        result.append(tc)
    return result


# NOTE: 「データ品質を確認して」のようにテーブル名の指定が無い依頼でも、
# モデルはプロンプト指示に反して "orders" 等のテーブルを勝手に推測して
# get_quality_metrics を呼んでしまうことが繰り返し確認された。ユーザーの
# 発言に、要求された table_fqn の実際の識別要素(テーブル名部分)が
# 一切含まれていない場合、これは推測によるでっち上げと判断し、
# get_data_quality_overview への呼び出しに差し替える。
def _redirect_unfounded_quality_lookup(tool_calls: list, user_text: str) -> list:
    result = []
    for tc in tool_calls:
        if tc["name"] == "get_quality_metrics":
            table_fqn = tc["args"].get("table_fqn", "")
            table_name = table_fqn.rsplit(".", 1)[-1].lower()
            if table_name and table_name not in user_text.lower():
                result.append({
                    "name": "get_data_quality_overview",
                    "args": {},
                    "id": tc["id"],
                    "type": "tool_call",
                })
                continue
        result.append(tc)
    return result


_PARTIAL_RESULT_MAX_CHARS = 1500


def _partial_result_notice(new_messages: list) -> str:
    """コンテキスト長超過で最終応答(自然文でのまとめ)の生成に失敗した際、
    それまでに取得できていた生データを見せる。LLM呼び出しは例外発生時点で
    1トークンも返さない同期API呼び出しのため、「部分的に生成された文章」は
    存在しない。ユーザーが実際に確認したいのは、そこまでに取得できていた
    データそのものであるため、ツール名の列挙だけでなく実際の結果も含める。"""
    tool_messages = [m for m in new_messages if isinstance(m, ToolMessage) and getattr(m, "name", None)]
    lines = [
        "⚠️ 応答のまとめ生成中にコンテキスト長の上限を超えたため、最後まで完了できませんでした。",
        "ここまでに取得できていたデータは以下の通りです(まとめ前の生データです):",
    ]
    for m in tool_messages:
        content = str(m.content)
        if len(content) > _PARTIAL_RESULT_MAX_CHARS:
            content = content[:_PARTIAL_RESULT_MAX_CHARS] + "...(省略)"
        lines.append(f"\n**{m.name}**\n```json\n{content}\n```")
    lines.append("\n質問の範囲を絞る(例:サイトや資産タイプを指定する)か、もう一度お試しください。")
    return "\n".join(lines)


def _invoke_subagent(agent_name: str, enable_thinking: bool, max_tokens: int, input_messages: list) -> list:
    """ツールバインディングされたLLMで手動のReActループを回す
    (create_react_agentのネストしたグラフ実行は使わない。理由は _SUBAGENT_CONFIGS
    のコメントを参照)。実際に呼ばれたツール名を status キューへ逐次通知する。"""
    tools, system_prompt = _SUBAGENT_CONFIGS[agent_name]
    tool_map = {t.name: t for t in tools}
    status_q = _status_queue_var.get()
    llm_with_tools = get_llm(enable_thinking=enable_thinking, max_tokens=max_tokens).bind_tools(tools)

    messages = [SystemMessage(content=system_prompt)] + list(input_messages)
    new_messages: list = []
    latest_human_text = next(
        (str(m.content) for m in reversed(input_messages) if isinstance(m, HumanMessage)), ""
    )
    for _ in range(_MAX_TOOL_ITERATIONS):
        try:
            ai_message = llm_with_tools.invoke(messages)
        except Exception as e:
            # NOTE: このターンで既にツール呼び出し等が進んでいた場合、コンテキスト長
            # 超過で例外を送出してすべて失うのではなく、まず出力トークン数(max_tokens)
            # をエラーメッセージから算出した安全な値まで縮小して要約の再試行を1回
            # 行う。以前はここで無条件に生JSONダンプへフォールバックしており、
            # 15件程度のツール結果でも要約生成が毎回コンテキスト長超過になる
            # ケース(例:「Aサイトのトピック一覧」)で必ずJSON生データ表示に
            # なってしまっていた。縮小できない、または縮小後も失敗する場合のみ
            # 打ち切り通知付きで返す。まだ一度もツールを呼べていない
            # (new_messages が空)場合は呼び出し元 _invoke_subagent_ensured の
            # 縮小リトライに委ねる。
            if not new_messages:
                raise
            safe_max = _shrink_max_tokens_for_error(str(e), max_tokens)
            if safe_max is None or safe_max <= 0:
                new_messages.append(AIMessage(content=_partial_result_notice(new_messages)))
                return new_messages
            log.warning("context_length_retry", node=agent_name, safe_max_tokens=safe_max)
            llm_with_tools = get_llm(enable_thinking=enable_thinking, max_tokens=safe_max).bind_tools(tools)
            try:
                ai_message = llm_with_tools.invoke(messages)
            except Exception:
                new_messages.append(AIMessage(content=_partial_result_notice(new_messages)))
                return new_messages
        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if not tool_calls:
            ai_message = _continue_if_truncated(llm_with_tools, messages, ai_message, status_q)
        messages.append(ai_message)
        new_messages.append(ai_message)
        if not tool_calls:
            break

        tool_calls = _inject_missing_topic_creation(tool_calls, messages[:-1])
        tool_calls = _redirect_unfounded_quality_lookup(tool_calls, latest_human_text)

        pending_tc = next(
            (tc for tc in tool_calls
             if tc["name"] in _CONFIRM_BEFORE_EXECUTE_TOOLS
             and not _already_confirmed(tc["args"].get("topic_name", ""), messages[:-1])),
            None,
        )
        if pending_tc:
            confirm_message = _confirmation_pending_message(pending_tc["args"])
            messages.append(confirm_message)
            new_messages.append(confirm_message)
            # 未確認の書き込みツールはこの応答内では一切実行しない
            # (同じ応答に含まれる他のツール呼び出しも合わせて中断する)。
            break

        broker_creation_failed = False
        for tc in tool_calls:
            if tc["name"] == "register_topic_metadata" and broker_creation_failed:
                # 直前の create_kafka_topic が失敗した場合、実体のないトピックを
                # OpenMetadata にだけ登録してしまわないよう、後続の登録もスキップする。
                result = {"error": "実ブローカーへのトピック作成に失敗したため、メタデータ登録をスキップしました", "success": False}
            else:
                tool_fn = tool_map.get(tc["name"])
                if tool_fn:
                    if status_q:
                        status_q.put(
                            _TOOL_STATUS_LABELS.get(tc["name"], f"{tc['name']} を実行しています...")
                        )
                    tool_args = _normalize_site_query(tc["name"], tc["args"], latest_human_text)
                    result = tool_fn.invoke(tool_args)
                    if tc["name"] == "create_kafka_topic" and not result.get("success"):
                        broker_creation_failed = True
                else:
                    result = {"error": f"unknown tool: {tc['name']}", "success": False}
            tool_message = ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=tc["id"],
                name=tc["name"],
            )
            messages.append(tool_message)
            new_messages.append(tool_message)
    return new_messages


def intent_classifier_node(state: AgentState) -> dict:
    messages = state["messages"]
    last_message = messages[-1]
    text = last_message.content if hasattr(last_message, "content") else str(last_message)
    intent, matched_pattern = classify_intent_detailed(text)

    # NOTE: create_kafka_topic 等の書き込みツールは、直前のターンで
    # 「承認が必要です」という確認メッセージを返し、ユーザーの次の返信
    # (「承認します」等)を待つ2段階フローになっている。しかしその返信の
    # 文面自体は「トピック」「作成」等のキーワードを含まないことが多く、
    # キーワードベースのルーターでは intent=unknown -> search_agent に
    # 誤ルーティングされ、schema_agent 側の承認待ち状態に到達できなかった
    # (create_kafka_topic が存在しないと誤回答する原因になっていた)。
    # 直前のAIメッセージが確認待ちプロンプトであれば、キーワード一致に
    # 関わらず schema_sync に留める。
    if intent == "unknown" and len(messages) >= 2:
        prev_ai = messages[-2]
        prev_text = prev_ai.content if hasattr(prev_ai, "content") else str(prev_ai)
        if isinstance(prev_text, str) and "承認が必要です" in prev_text:
            intent, matched_pattern = "schema_sync", "(pending_approval_continuation)"

    log.info(
        "intent_classified", intent=intent, matched_pattern=matched_pattern,
        thread_id=state.get("thread_id"),
    )
    return {"intent": intent, "matched_pattern": matched_pattern or ""}


_CONTEXT_LENGTH_RE = re.compile(
    r"maximum context length is (\d+) tokens.*?requested (\d+) tokens \((\d+) in the messages"
)


def _shrink_max_tokens_for_error(error_message: str, requested_max_tokens: int) -> int | None:
    """vLLMの'maximum context length'エラーメッセージから実際のプロンプト
    トークン数を読み取り、上限に収まる安全なmax_tokensを計算する。
    エラー形式が一致しない場合はNoneを返す。"""
    m = _CONTEXT_LENGTH_RE.search(error_message)
    if not m:
        return None
    model_limit, _requested_total, prompt_tokens = (int(g) for g in m.groups())
    # NOTE: マージンを大きく取りすぎると、ツール呼び出し後の大きいプロンプト
    # (既にモデル上限に近い)に対して安全なmax_tokensがマイナスになり、
    # 縮小自体を諦めてしまう(実際に観測済み)。この時点のプロンプトサイズは
    # 確定値であり、これ以上ふくらむのは今回の完了トークン分だけなので、
    # マージンは小さくてよい。フォールバック文言を返すより、たとえ短くても
    # 応答を切り詰めて返す方(truncation notice で利用者に伝わる)を優先し、
    # 諦める閾値も低くする。
    safety_margin = 100
    safe_max = model_limit - prompt_tokens - safety_margin
    if safe_max < 32:
        return None
    return min(safe_max, requested_max_tokens)


def chitchat_node(state: AgentState) -> dict:
    # NOTE: tools を一切バインドしない生の LLM 呼び出しのため、tool_choice="auto" を
    # 指定していても物理的にツール呼び出しが発生しえない (ReAct ループを完全に回避)。
    # 挨拶・雑談は毎回確実に高速応答させるためのショートカット経路。
    log.info("chitchat_invoked", thread_id=state.get("thread_id"))
    enable_thinking = state.get("enable_thinking", False)
    max_tokens = state.get("max_tokens", 1024)
    messages = _recent_messages(state)
    try:
        llm = get_llm(enable_thinking=enable_thinking, max_tokens=max_tokens)
        ai_message = llm.invoke(messages)
        ai_message = _continue_if_truncated(llm, messages, ai_message, _status_queue_var.get())
    except Exception as e:
        safe_max = _shrink_max_tokens_for_error(str(e), max_tokens)
        if safe_max is None:
            log.warning("context_length_giveup", node="chitchat", error=str(e))
            ai_message = AIMessage(
                content="すみません、応答が長くなりすぎたため生成できませんでした。もう一度お試しください。"
            )
        else:
            log.warning("context_length_retry", node="chitchat", safe_max_tokens=safe_max)
            llm = get_llm(enable_thinking=enable_thinking, max_tokens=safe_max)
            ai_message = llm.invoke(messages)
            ai_message = _continue_if_truncated(llm, messages, ai_message, _status_queue_var.get())
    return {
        "messages": [ai_message],
        "active_agent": "chitchat",
        "agent_output": {"messages": [ai_message.content]},
        "token_usage": sum_tokens([ai_message]),
    }


def _invoke_subagent_ensured(
    agent_name: str, enable_thinking: bool, max_tokens: int, input_messages: list
) -> list:
    """サブエージェントを実行し、必ず1件以上の新規メッセージを返す。

    高負荷時に応答生成が空文字を返してくることがあり(例外は発生しない)、その場合は
    同じ入力で再試行する。全て空ならフォールバックのAIMessageを返し、
    呼び出し側の result["messages"][-1] が IndexError にならないようにする。
    また、選択されたmax_tokensが会話履歴と合わせてモデルのコンテキスト長を
    超える場合は、エラーメッセージから安全なmax_tokensを算出して1回だけ
    縮小再試行する。"""
    current_max_tokens = max_tokens
    for attempt in range(3):
        try:
            new_messages = _invoke_subagent(agent_name, enable_thinking, current_max_tokens, input_messages)
        except Exception as e:
            safe_max = _shrink_max_tokens_for_error(str(e), current_max_tokens)
            if safe_max is None:
                # NOTE: 縮小してもコンテキスト長に収まらない(メッセージ側だけで
                # 上限に迫っている)場合、以前はここで即座に例外を再送出し、
                # 残りのリトライ回数があってもユーザーに生のAPIエラーが
                # 表示されてしまっていた。ここでは諦めてフォールバック文言を
                # 返す方を優先する。
                log.warning("context_length_giveup", node=agent_name, error=str(e))
                break
            log.warning("context_length_retry", node=agent_name, safe_max_tokens=safe_max)
            current_max_tokens = safe_max
            continue
        if new_messages:
            return new_messages
        log.warning("subagent_empty_reply_retry", attempt=attempt)
    return [AIMessage(content="すみません、応答が長くなりすぎたため生成できませんでした。質問の範囲を絞る(例:サイトや資産タイプを指定する)か、チャット設定の応答の長さを変更してもう一度お試しください。")]


# ツール付きサブエージェント(schema/search/registration)はシステムプロンプト+
# ツールスキーマ+ツール実行結果だけで実測 6000 トークン前後を消費し、8192の
# 上限に対する余地が乏しい。チャット設定で「高」(4096)や「最高」(8192)を
# 選択すると、それだけで即座にコンテキスト長を超えてしまうため、ツール付き
# エージェントに限りユーザー選択値をこの上限でクランプする(雑談(chitchat)は
# ツールスキーマを持たずプロンプトがずっと小さいため対象外)。
_TOOL_AGENT_MAX_TOKENS_CAP = 2048


def _clamp_tool_agent_max_tokens(requested_max_tokens: int) -> int:
    return min(requested_max_tokens, _TOOL_AGENT_MAX_TOKENS_CAP)


def schema_agent_node(state: AgentState) -> dict:
    log.info("schema_agent_invoked", thread_id=state.get("thread_id"))
    input_messages = _recent_messages(state)
    new_messages = _invoke_subagent_ensured(
        "schema",
        state.get("enable_thinking", False),
        _clamp_tool_agent_max_tokens(state.get("max_tokens", 1024)),
        input_messages,
    )

    # 承認フラグの検出（レスポンスに「承認」キーワードが含まれるか）。
    # create_kafka_topic は実際の外部ブローカーへの書き込みを伴うため、
    # registration_agent と同様の human-in-the-loop 経路を通す。
    last_content = new_messages[-1].content
    requires_approval = "承認" in last_content or "confirm" in last_content.lower()

    return {
        "messages": new_messages,
        "active_agent": "schema",
        "requires_approval": requires_approval,
        "approval_action": last_content if requires_approval else "",
        "agent_output": {"messages": [new_messages[-1].content]},
        "token_usage": sum_tokens(new_messages),
    }


def _build_user_context_message(state: AgentState) -> SystemMessage | None:
    user_id = state.get("user_id")
    if not user_id or user_id == "anonymous":
        return None
    # NOTE: Keycloak の "admin" ロールを持つユーザーは、OpenMetadata 側の
    # 実ユーザー名 "admin" のデータオーナーとして扱う (このワークショップ環境の
    # OpenMetadata データは全て "admin" ユーザーが所有者として登録されているため)。
    is_admin = "admin" in (state.get("user_roles") or [])
    owner_name = "admin" if is_admin else user_id
    return SystemMessage(
        content=(
            f"[context] ログイン中のユーザー名: {user_id}"
            f"{' (OpenMetadata 管理者権限あり)' if is_admin else ''}\n"
            f"「マイデータ」「自分のデータ」を尋ねられた場合は "
            f"get_my_data_assets を owner_name=\"{owner_name}\" で呼び出すこと。"
        )
    )


def search_agent_node(state: AgentState) -> dict:
    log.info("search_agent_invoked", thread_id=state.get("thread_id"))
    context_msg = _build_user_context_message(state)
    input_messages = ([context_msg] if context_msg else []) + _recent_messages(state)
    new_messages = _invoke_subagent_ensured(
        "search",
        state.get("enable_thinking", False),
        _clamp_tool_agent_max_tokens(state.get("max_tokens", 1024)),
        input_messages,
    )
    return {
        "messages": new_messages,
        "active_agent": "search",
        "agent_output": {"messages": [new_messages[-1].content]},
        "token_usage": sum_tokens(new_messages),
    }


def registration_agent_node(state: AgentState) -> dict:
    log.info("registration_agent_invoked", thread_id=state.get("thread_id"))
    input_messages = _recent_messages(state)
    output_messages = _invoke_subagent_ensured(
        "registration",
        state.get("enable_thinking", False),
        _clamp_tool_agent_max_tokens(state.get("max_tokens", 1024)),
        input_messages,
    )

    # 承認フラグの検出（レスポンスに「承認」キーワードが含まれるか）
    last_content = output_messages[-1].content
    requires_approval = "承認" in last_content or "confirm" in last_content.lower()

    return {
        "messages": output_messages,
        "active_agent": "registration",
        "requires_approval": requires_approval,
        "approval_action": last_content if requires_approval else "",
        "agent_output": {"messages": [m.content for m in output_messages[-1:]]},
        "token_usage": sum_tokens(output_messages),
    }


def human_approval_node(state: AgentState) -> dict:
    # NOTE: 実際の一時停止は create_graph() の interrupt_before=["human_approval"]
    # が担う(承認待ちの間、このノードは実行されない)。/api/v1/approve からの
    # 再開 (_graph.invoke(None, config)) で初めてこのノード本体が実行されるため、
    # ここで再度 NodeInterrupt を送出すると再開のたびに再中断してしまい、
    # invoke() が END まで到達せず None を返す原因になっていた(承認後に
    # "approve request failed: 500" となるバグ)。承認済みなのでそのまま完了させる。
    log.info("approval_granted", thread_id=state.get("thread_id"))
    return {"requires_approval": False}


def _check_approval(state: AgentState) -> str:
    if state.get("requires_approval"):
        return "needs_approval"
    return "done"


def create_graph(checkpointer=None) -> object:
    graph = StateGraph(AgentState)

    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("chitchat", chitchat_node)
    graph.add_node("schema_agent", schema_agent_node)
    graph.add_node("search_agent", search_agent_node)
    graph.add_node("registration_agent", registration_agent_node)
    graph.add_node("human_approval", human_approval_node)

    graph.set_entry_point("intent_classifier")

    graph.add_conditional_edges(
        "intent_classifier",
        route_to_agent,
        {
            "chitchat":     "chitchat",
            "schema":       "schema_agent",
            "search":       "search_agent",
            "registration": "registration_agent",
        },
    )

    graph.add_edge("chitchat", END)
    graph.add_edge("search_agent", END)

    graph.add_conditional_edges(
        "schema_agent",
        _check_approval,
        {
            "done":          END,
            "needs_approval": "human_approval",
        },
    )

    graph.add_conditional_edges(
        "registration_agent",
        _check_approval,
        {
            "done":          END,
            "needs_approval": "human_approval",
        },
    )

    graph.add_edge("human_approval", END)

    if checkpointer:
        checkpointer.setup()
        return graph.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])

    return graph.compile()
