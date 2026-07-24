"""
create_kafka_topic が成功した後、モデルが register_topic_metadata を呼ばずに
ターンを終えてしまう(実ブローカー上にはトピックが作られるが、OpenMetadata
には一切登録されない)不具合の回帰テスト。

_invoke_subagent は、create_kafka_topic 成功後にツール呼び出し無しの応答が
返ってきた場合、まずリマインダーを注入してモデルにもう一度register_topic_metadata
を呼ばせようとし、それでも呼ばなければ「完了しました」と誤って報告せず、
明示的な警告メッセージに差し替える。
"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.orchestrator import graph as graph_module


class _FakeTool:
    def __init__(self, name, result_fn):
        self.name = name
        self._result_fn = result_fn

    def invoke(self, args):
        return self._result_fn(args)


class _FakeLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return self._responses.pop(0)


def _make_tools():
    create_result = {
        "topic_name": "order-test3",
        "service_name": "external-shop-cluster-kafka-asite:9094",
        "created": True,
        "managed": True,
        "success": True,
    }
    register_result = {"fqn": "external-shop-cluster-kafka-asite:9094.order-test3", "created": True, "success": True}
    tools = [
        _FakeTool("create_kafka_topic", lambda args: create_result),
        _FakeTool("register_topic_metadata", lambda args: register_result),
        _FakeTool("topic_exists", lambda args: {"exists": False, "success": True}),
    ]
    return tools


def _filler_tool_call(call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "topic_exists", "args": {"topic_name": "order-test3"}, "id": call_id, "type": "tool_call"}],
    )


def test_reminder_is_injected_and_model_then_registers_metadata(monkeypatch):
    tools = _make_tools()
    monkeypatch.setitem(graph_module._SUBAGENT_CONFIGS, "schema", (tools, "system prompt"))

    create_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "create_kafka_topic",
            "args": {"topic_name": "order-test3", "service_name": "external-shop-cluster-kafka-asite:9094"},
            "id": "1", "type": "tool_call",
        }],
    )
    # モデルがここでツール呼び出し無しの応答を返す(バグを再現する箇所)。
    premature_stop = AIMessage(content="トピックを追加しました。")
    # リマインダーを受け取った後、モデルが register_topic_metadata を呼ぶ。
    register_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "register_topic_metadata",
            "args": {
                "topic_name": "order-test3",
                "service_name": "external-shop-cluster-kafka-asite:9094",
                "description": "test",
            },
            "id": "2", "type": "tool_call",
        }],
    )
    final_reply = AIMessage(content="トピックを作成し、OpenMetadataにも登録しました。")

    fake_llm = _FakeLLM([create_call, premature_stop, register_call, final_reply])
    monkeypatch.setattr(graph_module, "get_llm", lambda enable_thinking=False, max_tokens=1024: fake_llm)

    result = graph_module._invoke_subagent(
        "schema", False, 1024,
        [
            HumanMessage(content="Aサイトに order-test3 トピックを追加して"),
            AIMessage(content="`order-test3` を新規作成します。承認をお願いします。"),
            HumanMessage(content="承認します。"),
        ],
    )

    tool_names_called = [m.name for m in result if isinstance(m, ToolMessage)]
    assert tool_names_called == ["create_kafka_topic", "register_topic_metadata"]
    assert result[-1].content == final_reply.content


def test_gap_notice_replaces_false_success_when_model_never_registers(monkeypatch):
    tools = _make_tools()
    monkeypatch.setitem(graph_module._SUBAGENT_CONFIGS, "schema", (tools, "system prompt"))

    create_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "create_kafka_topic",
            "args": {"topic_name": "order-test3", "service_name": "external-shop-cluster-kafka-asite:9094"},
            "id": "1", "type": "tool_call",
        }],
    )
    # リマインダー後も、モデルはツールを呼ばずに完了を自称し続ける。
    premature_stop = AIMessage(content="トピックを追加しました。")
    still_no_tool = AIMessage(content="トピックを追加しました。")

    fake_llm = _FakeLLM([create_call, premature_stop, still_no_tool])
    monkeypatch.setattr(graph_module, "get_llm", lambda enable_thinking=False, max_tokens=1024: fake_llm)

    result = graph_module._invoke_subagent(
        "schema", False, 1024,
        [
            HumanMessage(content="Aサイトに order-test3 トピックを追加して"),
            AIMessage(content="`order-test3` を新規作成します。承認をお願いします。"),
            HumanMessage(content="承認します。"),
        ],
    )

    tool_names_called = [m.name for m in result if isinstance(m, ToolMessage)]
    assert tool_names_called == ["create_kafka_topic"]
    # モデルの「追加しました」を鵜呑みにせず、登録が未完了である旨の警告に差し替える。
    assert "OpenMetadata" in result[-1].content
    assert "order-test3" in result[-1].content
    assert result[-1].content != "トピックを追加しました。"


def test_gap_notice_when_loop_exhausts_before_registration_call(monkeypatch):
    """topic_exists + GitHub調査(タイムアウト含む)+ create_kafka_topic だけで
    _MAX_TOOL_ITERATIONS を使い切り、register_topic_metadata を呼ぶ前にループが
    (breakを経由せず)終了してしまうケースの回帰テスト。以前はこの場合、
    new_messages の最後が生のToolMessage(JSON)のままユーザーへの最終回答に
    なってしまっていた。"""
    tools = _make_tools()
    monkeypatch.setitem(graph_module._SUBAGENT_CONFIGS, "schema", (tools, "system prompt"))

    create_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "create_kafka_topic",
            "args": {"topic_name": "order-test3", "service_name": "external-shop-cluster-kafka-asite:9094"},
            "id": "create-1", "type": "tool_call",
        }],
    )
    # _MAX_TOOL_ITERATIONS(8) 回のうち最後の1回を create_kafka_topic に使い、
    # それより前は全て他のツール呼び出しで埋め尽くす(GitHub調査等を模す)。
    responses = [_filler_tool_call(f"filler-{i}") for i in range(graph_module._MAX_TOOL_ITERATIONS - 1)]
    responses.append(create_call)

    fake_llm = _FakeLLM(responses)
    monkeypatch.setattr(graph_module, "get_llm", lambda enable_thinking=False, max_tokens=1024: fake_llm)

    result = graph_module._invoke_subagent(
        "schema", False, 1024,
        [
            HumanMessage(content="Aサイトに order-test3 トピックを追加して"),
            AIMessage(content="`order-test3` を新規作成します。承認をお願いします。"),
            HumanMessage(content="承認します。"),
        ],
    )

    tool_names_called = [m.name for m in result if isinstance(m, ToolMessage)]
    assert tool_names_called[-1] == "create_kafka_topic"
    assert "register_topic_metadata" not in tool_names_called
    # 最後は生のToolMessageではなく、登録未完了を知らせる自然文のAIMessageであること。
    assert isinstance(result[-1], AIMessage)
    assert "OpenMetadata" in result[-1].content
    assert "order-test3" in result[-1].content
