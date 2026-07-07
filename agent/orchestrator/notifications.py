import asyncio
import json
import os
import threading
from collections import deque

import structlog
from kafka import KafkaConsumer

log = structlog.get_logger()

_RECENT_MAXLEN = 50


class NotificationBridge:
    """pipeline-notifications トピックを購読し、SSE購読者へ配信する。

    kafka-python は同期APIのためバックグラウンドスレッドで購読し、
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

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._thread = threading.Thread(target=self._consume_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def recent(self) -> list[dict]:
        return list(self._recent)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _consume_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                consumer = KafkaConsumer(
                    self._topic,
                    bootstrap_servers=self._bootstrap_servers,
                    group_id="ai-agent-orchestrator-notifications",
                    auto_offset_reset="latest",
                    enable_auto_commit=True,
                    consumer_timeout_ms=1000,
                    value_deserializer=lambda v: v.decode("utf-8"),
                )
                log.info("notification_consumer_connected", topic=self._topic)
                while not self._stop_event.is_set():
                    for record in consumer:
                        self._handle_message(record.value)
                        if self._stop_event.is_set():
                            break
            except Exception as e:
                log.warning("notification_consumer_error", error=str(e))
                self._stop_event.wait(5)

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
