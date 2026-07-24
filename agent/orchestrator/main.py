import asyncio
import base64
import json
import os
import queue
import uuid
from contextlib import ExitStack, asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel

load_dotenv()

from agent.common.llm import DEFAULT_MAX_TOKENS_LEVEL, MAX_TOKENS_LEVELS
from agent.orchestrator.graph import _status_queue_var, create_graph
from agent.orchestrator.notifications import (
    get_bridge as get_notification_bridge,
)
from agent.orchestrator.scheduled_tasks import (
    get_bridge as get_scheduled_task_bridge,
)
from tools.common.history_store import get_history_store
from tools.common.settings_store import get_settings_store

log = structlog.get_logger()

_MAX_TOKENS_SETTINGS_KEYS = {
    "low": "max_tokens_level_low",
    "medium": "max_tokens_level_medium",
    "high": "max_tokens_level_high",
    "max": "max_tokens_level_max",
}


def _current_max_tokens_levels() -> dict:
    """設定画面から変更された値があればそれを使い、無ければ既定値を使う。"""
    store = get_settings_store()
    levels = dict(MAX_TOKENS_LEVELS)
    if store:
        for level, key in _MAX_TOKENS_SETTINGS_KEYS.items():
            value = store.get(key)
            if value is not None:
                levels[level] = int(value)
    return levels

_graph = None
_checkpointer_stack = ExitStack()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph
    log.info("initializing_graph")

    checkpointer = None
    db_url = os.environ.get("AGENT_DB_URL")
    if db_url:
        # PostgresSaver.from_conn_string はコンテキストマネージャなので
        # アプリのライフスパンに合わせて ExitStack でコネクションを保持する
        # Pod起動直後は DNS/ネットワークがまだ安定していないことがあるためリトライする
        last_error = None
        for attempt in range(30):
            try:
                checkpointer = _checkpointer_stack.enter_context(
                    PostgresSaver.from_conn_string(db_url)
                )
                last_error = None
                break
            except Exception as e:
                last_error = e
                log.warning("db_connect_retry", attempt=attempt, error=str(e))
                await asyncio.sleep(5)
        if last_error:
            raise last_error

    _graph = create_graph(checkpointer=checkpointer)
    log.info("graph_initialized")

    get_notification_bridge().start(asyncio.get_event_loop())
    get_scheduled_task_bridge().start(asyncio.get_event_loop())

    yield
    get_notification_bridge().stop()
    get_scheduled_task_bridge().stop()
    _checkpointer_stack.close()


app = FastAPI(
    title="AI Agent Orchestrator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = ""
    user_id: str = "anonymous"
    user_roles: list[str] = ["viewer"]
    # チャット画面の設定ボタンから毎回選べるLLM設定
    enable_thinking: bool = False
    max_tokens_level: str = DEFAULT_MAX_TOKENS_LEVEL


def _identity_from_bearer_token(request: Request) -> tuple[str | None, list[str]]:
    """Authorization ヘッダの Keycloak JWT からユーザー名とロールを取り出す。
    NOTE: 署名検証は行わない (認可判断には使わず、表示・データ絞り込みの
    UX 用途のみ)。認可が必要な操作は Business API 側の OIDC 検証に従う。"""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None, []
    token = auth.split(" ", 1)[1]
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        username = claims.get("preferred_username")
        roles = claims.get("realm_access", {}).get("roles", [])
        return username, roles
    except Exception:
        return None, []


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    intent: str
    active_agent: str
    requires_approval: bool = False
    approval_action: str = ""
    token_usage: int = 0


class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool
    user_id: str = "anonymous"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    if _graph is None:
        raise HTTPException(503, "Graph not initialized")
    return {"status": "ready"}


# ノード名 -> 検索中表示用の日本語ラベル
_NODE_STATUS_LABELS = {
    "chitchat":           "応答を生成しています...",
    "schema_agent":       "スキーマ情報を検索しています...",
    "search_agent":       "データ資産を検索しています...",
    "registration_agent": "登録処理を実行しています...",
    "human_approval":     "承認を待っています...",
}

# intent_classifier の判定結果 -> 表示用の日本語ラベル。
# classify_intent はキーワード正規表現による瞬時の判定のため、
# 「意図を判定しています...」という固定文言のままだと何も進んでいないように
# 見えてしまう。判定が完了した時点で実際に何と判定されたかを示す。
_INTENT_LABELS = {
    "chitchat":        "雑談",
    "schema_sync":     "スキーマ同期",
    "metadata_search": "メタデータ検索",
    "metadata_update": "メタデータ更新",
    "data_register":   "データ登録",
    "data_search":     "データ検索",
    "data_update":      "データ更新",
    "lineage_check":   "データリネージ確認",
    "platform_ops":    "プラットフォーム操作",
    "unknown":         "判定不能(検索エージェントへフォールバック)",
}


def _invoke_graph(req: ChatRequest, thread_id: str, config: dict, status_q: queue.Queue) -> dict:
    final_state: dict = {}
    # NOTE: invoke() ではなく stream(stream_mode="updates") を使い、ノードが
    # 完了するたびに status_q へ通知する (3秒以上かかる場合に何を検索中か
    # フロントエンドへ表示するため)。実行は一度きりで、副作用が重複することはない。
    # status_queue は config["configurable"] 経由で渡そうとしたが、
    # PostgresSaver チェックポインタがそれ以外のキーを除去してしまうため、
    # contextvars 経由でサブエージェントのノード関数に渡す (この関数は
    # run_in_executor の同一ワーカースレッド内で最後まで実行されるため、
    # スレッドをまたがず伝播できる)。
    _status_queue_var.set(status_q)
    max_tokens_levels = _current_max_tokens_levels()
    max_tokens = max_tokens_levels.get(req.max_tokens_level, max_tokens_levels[DEFAULT_MAX_TOKENS_LEVEL])
    for chunk in _graph.stream(
        {
            "messages": [HumanMessage(content=req.message)],
            "thread_id": thread_id,
            "user_id": req.user_id,
            "user_roles": req.user_roles,
            "enable_thinking": req.enable_thinking,
            "max_tokens": max_tokens,
        },
        config=config,
        stream_mode="updates",
    ):
        for node_name, node_output in chunk.items():
            if node_name == "intent_classifier" and isinstance(node_output, dict):
                intent = node_output.get("intent", "unknown")
                label = _INTENT_LABELS.get(intent, intent)
                matched_pattern = node_output.get("matched_pattern") or ""
                if matched_pattern:
                    # 正規表現をそのまま出すと読みにくいので簡易的に整形する
                    readable = matched_pattern.replace(".*", "…").strip("^$")
                    status_q.put(f"「{label}」と判定しました(「{readable}」に一致)。処理を開始します...")
                else:
                    status_q.put(f"「{label}」と判定しました。処理を開始します...")
            else:
                status_q.put(_NODE_STATUS_LABELS.get(node_name, f"{node_name} を実行しています..."))
            if isinstance(node_output, dict):
                final_state.update(node_output)
    return final_state


@app.post("/api/v1/chat")
async def chat(req: ChatRequest, request: Request):
    thread_id = req.thread_id or str(uuid.uuid4())
    # NOTE: chat-ui は現状 user_id/user_roles を body に含めないため、
    # Authorization ヘッダの Keycloak トークンから解決する。
    username, roles = _identity_from_bearer_token(request)
    if username:
        req.user_id = username
        req.user_roles = roles
    config = {
        "configurable": {
            "thread_id": thread_id,
        },
        "recursion_limit": 15,
    }

    log.info("chat_request", thread_id=thread_id, user=req.user_id)

    async def event_generator():
        loop = asyncio.get_event_loop()
        status_q: queue.Queue = queue.Queue()
        future = loop.run_in_executor(None, _invoke_graph, req, thread_id, config, status_q)
        # CPU推論は数十秒かかることがあるため、手前のロードバランサの
        # アイドルタイムアウト(接続に一定時間データが流れないと切断される)に
        # 引っかからないよう、完了まで定期的にコメント行を流し続ける。
        # NOTE: sleep(15) を直接ループ条件のポーリング間隔にすると、実際の
        # 処理が数秒で終わっても次のポーリングまで最大15秒待たされてしまう
        # (chitchat 等の高速応答でも常に15秒かかる不具合の原因だった)。
        # ポーリング自体は短い間隔で行い、キープアライブ行の送出だけを
        # 15秒間隔に間引く。
        KEEPALIVE_INTERVAL = 15
        POLL_INTERVAL = 0.5
        STATUS_DISPLAY_THRESHOLD = 3.0
        elapsed_since_keepalive = 0.0
        elapsed_total = 0.0
        while not future.done():
            await asyncio.sleep(POLL_INTERVAL)
            elapsed_since_keepalive += POLL_INTERVAL
            elapsed_total += POLL_INTERVAL
            if elapsed_since_keepalive >= KEEPALIVE_INTERVAL:
                yield ": keep-alive\n\n"
                elapsed_since_keepalive = 0.0

            # 3秒以上かかっている場合のみ、現在何を実行中か通知する
            if elapsed_total >= STATUS_DISPLAY_THRESHOLD:
                latest_status = None
                while not status_q.empty():
                    latest_status = status_q.get_nowait()
                if latest_status:
                    yield f"data: {json.dumps({'status': latest_status, 'thread_id': thread_id})}\n\n"

        try:
            result = future.result()
        except Exception as e:
            log.error("chat_failed", error=str(e), thread_id=thread_id)
            yield f"data: {json.dumps({'error': f'エージェント実行エラー: {e}', 'thread_id': thread_id})}\n\n"
            return

        messages = result.get("messages") or []
        if not messages:
            log.error("chat_empty_result", thread_id=thread_id)
            yield f"data: {json.dumps({'error': 'エージェント実行エラー: 応答を生成できませんでした', 'thread_id': thread_id})}\n\n"
            return
        last_message = messages[-1]
        reply = last_message.content if hasattr(last_message, "content") else str(last_message)

        history_store = get_history_store()
        if history_store and req.user_id:
            history_store.log_turn(thread_id, req.user_id, "user", req.message)
            history_store.log_turn(thread_id, req.user_id, "assistant", reply)

        payload = ChatResponse(
            thread_id=thread_id,
            reply=reply,
            intent=result.get("intent", "unknown"),
            active_agent=result.get("active_agent", ""),
            requires_approval=result.get("requires_approval", False),
            approval_action=result.get("approval_action", ""),
            token_usage=result.get("token_usage", 0),
        ).dict()
        yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/v1/approve")
def approve(req: ApprovalRequest):
    if not req.approved:
        return {"thread_id": req.thread_id, "status": "rejected"}

    config = {"configurable": {"thread_id": req.thread_id}}
    log.info("approval_received", thread_id=req.thread_id, user=req.user_id)

    try:
        result = _graph.invoke(None, config=config)
        last_message = result["messages"][-1]
        reply = last_message.content if hasattr(last_message, "content") else str(last_message)
        return {"thread_id": req.thread_id, "status": "approved", "reply": reply}
    except Exception as e:
        log.error("approval_resume_failed", error=str(e))
        raise HTTPException(500, f"承認後の実行エラー: {e!s}")


@app.get("/api/v1/notifications/recent")
def notifications_recent():
    return {"notifications": get_notification_bridge().recent()}


@app.get("/api/v1/notifications/stream")
async def notifications_stream():
    bridge = get_notification_bridge()
    queue = bridge.subscribe()

    async def event_generator():
        try:
            # 接続直後は既知の直近通知をまとめて送る
            for item in bridge.recent():
                yield f"data: {json.dumps(item)}\n\n"
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bridge.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/v1/scheduled-tasks/recent")
def scheduled_tasks_recent():
    return {"tasks": get_scheduled_task_bridge().recent()}


class ScheduledTaskSettings(BaseModel):
    interval_seconds: int | None = None
    backoff_failure_threshold: int | None = None
    backoff_interval_seconds: int | None = None


@app.get("/api/v1/settings/scheduled-task")
def get_scheduled_task_settings():
    return get_scheduled_task_bridge().get_settings()


@app.put("/api/v1/settings/scheduled-task")
def update_scheduled_task_settings(req: ScheduledTaskSettings):
    return get_scheduled_task_bridge().update_settings(
        interval_seconds=req.interval_seconds,
        backoff_failure_threshold=req.backoff_failure_threshold,
        backoff_interval_seconds=req.backoff_interval_seconds,
    )


class MaxTokensSettings(BaseModel):
    low: int | None = None
    medium: int | None = None
    high: int | None = None
    max: int | None = None


@app.get("/api/v1/settings/max-tokens")
def get_max_tokens_settings():
    return _current_max_tokens_levels()


@app.put("/api/v1/settings/max-tokens")
def update_max_tokens_settings(req: MaxTokensSettings):
    store = get_settings_store()
    updates = req.model_dump(exclude_none=True)
    if store:
        for level, value in updates.items():
            store.set(_MAX_TOKENS_SETTINGS_KEYS[level], str(value))
    return _current_max_tokens_levels()


@app.get("/api/v1/scheduled-tasks/stream")
async def scheduled_tasks_stream():
    bridge = get_scheduled_task_bridge()
    queue = bridge.subscribe()

    async def event_generator():
        try:
            for item in bridge.recent():
                yield f"data: {json.dumps(item)}\n\n"
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bridge.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    thread_id = str(uuid.uuid4())
    log.info("websocket_connected", thread_id=thread_id)

    try:
        while True:
            data = await ws.receive_json()
            message = data.get("message", "")
            if not message:
                continue

            config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 15}

            try:
                result = _graph.invoke(
                    {
                        "messages": [HumanMessage(content=message)],
                        "thread_id": thread_id,
                        "user_id": data.get("user_id", "anonymous"),
                        "user_roles": data.get("user_roles", ["viewer"]),
                    },
                    config=config,
                )
                last = result["messages"][-1]
                await ws.send_json({
                    "thread_id": thread_id,
                    "reply": last.content if hasattr(last, "content") else str(last),
                    "intent": result.get("intent", "unknown"),
                    "requires_approval": result.get("requires_approval", False),
                })
            except Exception as e:
                await ws.send_json({"error": str(e), "thread_id": thread_id})

    except WebSocketDisconnect:
        log.info("websocket_disconnected", thread_id=thread_id)
