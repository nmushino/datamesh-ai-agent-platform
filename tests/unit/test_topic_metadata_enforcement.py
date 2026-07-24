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
    ]
    return tools


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
