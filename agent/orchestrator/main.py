import os
import time
import uuid
import structlog
from contextlib import asynccontextmanager, ExitStack
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver

from dotenv import load_dotenv
load_dotenv()

from agent.orchestrator.graph import create_graph

log = structlog.get_logger()

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
                time.sleep(5)
        if last_error:
            raise last_error

    _graph = create_graph(checkpointer=checkpointer)
    log.info("graph_initialized")
    yield
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


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    intent: str
    active_agent: str
    requires_approval: bool = False
    approval_action: str = ""


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


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {
        "configurable": {
            "thread_id": thread_id,
        },
        "recursion_limit": 15,
    }

    log.info("chat_request", thread_id=thread_id, user=req.user_id)

    try:
        result = _graph.invoke(
            {
                "messages": [HumanMessage(content=req.message)],
                "thread_id": thread_id,
                "user_id": req.user_id,
                "user_roles": req.user_roles,
            },
            config=config,
        )
    except Exception as e:
        log.error("chat_failed", error=str(e), thread_id=thread_id)
        raise HTTPException(500, f"エージェント実行エラー: {str(e)}")

    last_message = result["messages"][-1]
    reply = last_message.content if hasattr(last_message, "content") else str(last_message)

    return ChatResponse(
        thread_id=thread_id,
        reply=reply,
        intent=result.get("intent", "unknown"),
        active_agent=result.get("active_agent", ""),
        requires_approval=result.get("requires_approval", False),
        approval_action=result.get("approval_action", ""),
    )


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
        raise HTTPException(500, f"承認後の実行エラー: {str(e)}")


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
