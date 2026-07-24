"""
_invoke_subagent が、ツール実行後の要約生成でコンテキスト長超過に遭遇した際、
即座に生JSONダンプ(_partial_result_notice)へフォールバックせず、まず
max_tokens を縮小して要約を再試行することを確認するテスト。
"""
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.orchestrator import graph as graph_module


class _FakeTool:
    def __init__(self, name, result):
        self.name = name
        self._result = result

    def invoke(self, args):
        return self._result


class _FakeLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def test_context_length_error_after_tool_call_shrinks_and_retries(monkeypatch):
    tool_result = {"assets": [{"name": "eighty-six"}], "total": 15, "success": True}
    fake_tool = _FakeTool("search_data_assets", tool_result)
    monkeypatch.setitem(
        graph_module._SUBAGENT_CONFIGS, "search", ([fake_tool], "system prompt")
    )

    tool_call_message = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_data_assets", "args": {"query": "*"}, "id": "1", "type": "tool_call"}
        ],
    )
    # messages 側だけで 6000 トークン、上限 8192 なので安全な余地(6192-100=2092)が
    # まだ残っているケース。
    context_length_error = Exception(
        "maximum context length is 8192 tokens, however you requested 3000 tokens "
        "(6000 in the messages, 3000 in the completion)"
    )
    summary_message = AIMessage(content="### 📨 Kafkaトピック (15件)\n| 名前 | ... |")

    fake_llm = _FakeLLM([tool_call_message, context_length_error, summary_message])

    captured_max_tokens = []

    def fake_get_llm(enable_thinking=False, max_tokens=1024):
        captured_max_tokens.append(max_tokens)
        return fake_llm

    monkeypatch.setattr(graph_module, "get_llm", fake_get_llm)

    result = graph_module._invoke_subagent(
        "search", False, 2048, [HumanMessage(content="Aサイトのトピック一覧")]
    )

    # 生JSONダンプの打ち切り通知ではなく、縮小リトライ後の要約結果が返る。
    assert result[-1].content == summary_message.content
    assert "コンテキスト長の上限を超えたため" not in str(result[-1].content)
    # 縮小後の max_tokens は本来 8192 - 6000 - 100 = 2092 だが、呼び出し元の
    # 元々の max_tokens (2048) を超えないよう min() でキャップされる。
    assert captured_max_tokens[-1] == 2048


def test_context_length_error_gives_up_when_messages_already_at_limit(monkeypatch):
    tool_result = {"assets": [{"name": "eighty-six"}], "total": 15, "success": True}
    fake_tool = _FakeTool("search_data_assets", tool_result)
    monkeypatch.setitem(
        graph_module._SUBAGENT_CONFIGS, "search", ([fake_tool], "system prompt")
    )

    tool_call_message = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_data_assets", "args": {"query": "*"}, "id": "1", "type": "tool_call"}
        ],
    )
    # messages だけで既に上限を超えており、縮小の余地がないケース。
    context_length_error = Exception(
        "maximum context length is 8192 tokens, however you requested 9000 tokens "
        "(8500 in the messages, 500 in the completion)"
    )

    fake_llm = _FakeLLM([tool_call_message, context_length_error])

    monkeypatch.setattr(graph_module, "get_llm", lambda enable_thinking=False, max_tokens=1024: fake_llm)

    result = graph_module._invoke_subagent(
        "search", False, 2048, [HumanMessage(content="Aサイトのトピック一覧")]
    )

    assert "コンテキスト長の上限を超えたため" in str(result[-1].content)


def test_partial_result_notice_is_a_minimal_summary_not_a_full_json_dump(monkeypatch):
    """打ち切り通知は、以前は各ツール結果の生JSON(最大1500文字/件)をそのまま
    並べていたため冗長すぎた。成功/失敗と短いエラー概要だけの1行にまとめる。"""
    huge_content = json.dumps({"error": "x" * 5000, "success": False})
    ok_content = json.dumps({"exists": False, "success": True})
    new_messages = [
        ToolMessage(content=huge_content, tool_call_id="1", name="topic_exists"),
        ToolMessage(content=ok_content, tool_call_id="2", name="list_github_org_repos"),
    ]

    notice = graph_module._partial_result_notice(new_messages)

    assert len(notice) < 1000
    assert "topic_exists" in notice
    assert "list_github_org_repos" in notice
    assert "x" * 200 not in notice
