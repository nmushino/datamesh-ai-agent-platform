import asyncio
import json
import os
import subprocess
import threading
from collections import deque

import structlog

log = structlog.get_logger()

_RECENT_MAXLEN = 50

# kafka-python はこの Kafka 4.x (KRaft) ブローカーと ApiVersions ネゴシエーションが
# 非互換で NodeNotReadyError/NoBrokersAvailable になることを確認済み(tools/kafka/
# admin_tools.py と同じ問題)。この購読側は create_kafka_topic のような単発の
# admin操作と異なり長時間ストリーミングし続けるため、kafka-topics.sh と同様の
# 単発subprocess呼び出しには置き換えられない。ここでは同梱の Kafka クライアント
# 配布物の kafka-console-consumer.sh を長時間実行のsubprocessとして起動し、
# 標準出力を1行ずつ読み取ってブリッジする方式にする。
_KAFKA_CONSOLE_CONSUMER_CMD = "kafka-console-consumer.sh"

# 接続失敗時のバックオフ。以前は5秒固定で無限リトライしており、ブローカーが
# 存在しない/到達不能な設定ミスの場合に高頻度の再接続ループとなってCPUを
# 消費し続け、同じPod内で実行される kafka-topics.sh (JVM起動) のタイムアウトを
# 誘発する一因になっていた。指数バックオフで上限を設ける。
_INITIAL_BACKOFF_SECONDS = 5
_MAX_BACKOFF_SECONDS = 120


class NotificationBridge:
    """pipeline-notifications トピックを購読し、SSE購読者へ配信する。

    kafka-console-consumer.sh (CLI) を長時間実行のsubprocessとして起動し、
    バックグラウンドスレッドで標準出力を1行ずつ読み取って
    asyncio.Queue 経由で各SSE接続(非同期)へブリッジする。
    """

    def __init__(self, topic: str, bootstrap_servers: str):
        self._topic = topic
        self._bootstrap_servers = bootstrap_servers
        self._recent: deque[dict] = deque(maxlen=_RECENT_MAXLEN)
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._process: subprocess.Popen | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._thread = threading.Thread(target=self._consume_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._process is not None:
            self._process.terminate()

    def recent(self) -> list[dict]:
        return list(self._recent)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _consume_loop(self) -> None:
        backoff = _INITIAL_BACKOFF_SECONDS
        while not self._stop_event.is_set():
            try:
                self._process = subprocess.Popen(
                    [
                        _KAFKA_CONSOLE_CONSUMER_CMD,
                        "--bootstrap-server", self._bootstrap_servers,
                        "--topic", self._topic,
                        "--group", "ai-agent-orchestrator-notifications",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
                log.info("notification_consumer_connected", topic=self._topic)
                backoff = _INITIAL_BACKOFF_SECONDS
                for line in self._process.stdout:
                    if self._stop_event.is_set():
                        break
                    line = line.strip()
                    if line:
                        self._handle_message(line)
                self._process.wait(timeout=5)
                if self._process.returncode != 0 and not self._stop_event.is_set():
                    raise RuntimeError(f"kafka-console-consumer.sh exited with code {self._process.returncode}")
            except Exception as e:
                log.warning("notification_consumer_error", error=str(e))
                if self._process is not None:
                    self._process.kill()
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    def _handle_message(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw}
        self.push(payload)

    def push(self, payload: dict) -> None:
        """pipeline-notifications トピック以外(定期チェックのエラー等)からも
        通知ベルへ直接配信するための公開メソッド。"""
        self._recent.append(payload)
        log.info("notification_received", payload=payload)
        if self._loop is None:
            return
        for queue in list(self._subscribers):
            self._loop.call_soon_threadsafe(queue.put_nowait, payload)


_bridge: NotificationBridge | None = None


def get_bridge() -> NotificationBridge:
    global _bridge
    if _bridge is None:
        _bridge = NotificationBridge(
            topic=os.environ.get("NOTIFICATIONS_TOPIC", "pipeline-notifications"),
            bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        )
    return _bridge
