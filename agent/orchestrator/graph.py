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


def _normalize_site_query(tool_name: str, args: dict) -> dict:
    """search_data_assets の query に「Aサイト」等の日本語がそのまま
    残っている場合、FQN ワイルドカードクエリに強制的に書き換える。
    プロンプトでの指示だけでは徹底されないことがあり(他サイトの複製先
    説明にも一致してしまい、結果が肥大化してコンテキスト長を超える
    原因になっていた)、確実性のためコード側でも補正する。"""
    if tool_name != "search_data_assets":
        return args
    query = args.get("query", "")
    for keyword, fqn_part in _SITE_KEYWORD_TO_FQN_PART.items():
        if keyword in query and "fullyQualifiedName:" not in query:
            new_args = dict(args)
            new_args["query"] = f"fullyQualifiedName:*{fqn_part}*"
            log.warning("site_query_normalized", original_query=query, new_query=new_args["query"])
            return new_args
    return args


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
    for _ in range(_MAX_TOOL_ITERATIONS):
        ai_message = llm_with_tools.invoke(messages)
        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if not tool_calls:
            ai_message = _continue_if_truncated(llm_with_tools, messages, ai_message, status_q)
        messages.append(ai_message)
        new_messages.append(ai_message)
        if not tool_calls:
            break
        for tc in tool_calls:
            tool_fn = tool_map.get(tc["name"])
            if tool_fn:
                if status_q:
                    status_q.put(
                        _TOOL_STATUS_LABELS.get(tc["name"], f"{tc['name']} を実行しています...")
                    )
                tool_args = _normalize_site_query(tc["name"], tc["args"])
                result = tool_fn.invoke(tool_args)
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
    last_message = state["messages"][-1]
    text = last_message.content if hasattr(last_message, "content") else str(last_message)
    intent, matched_pattern = classify_intent_detailed(text)
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
    return {
        "messages": new_messages,
        "active_agent": "schema",
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
    from langgraph.errors import NodeInterrupt
    log.info("waiting_for_approval", thread_id=state.get("thread_id"))
    raise NodeInterrupt(
        f"承認が必要です。以下の操作を承認してください:\n{state.get('approval_action', '')}"
    )


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
    graph.add_edge("schema_agent", END)
    graph.add_edge("search_agent", END)

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
