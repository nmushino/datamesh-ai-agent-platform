import asyncio
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timezone

import structlog

from tools.common.client import get_openmetadata_client

log = structlog.get_logger()

_RECENT_MAXLEN = 50


class ScheduledTaskBridge:
    """OpenMetadataのデータ品質・スキーマ変更を定期チェックし、SSE購読者へ配信する。

    Kafkaのような外部イベント源ではなく、Agent自身がバックグラウンドスレッドで
    一定間隔ごとにOpenMetadataへ問い合わせて前回結果と比較する、自発的な定期実行タスク。
    """

    def __init__(self, table_fqns: list[str], interval_seconds: int):
        self._table_fqns = table_fqns
        self._interval_seconds = interval_seconds
        self._recent: deque[dict] = deque(maxlen=_RECENT_MAXLEN)
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # fqn -> {"columns": int, "qualityScore": float} 前回チェック時のスナップショット
        self._snapshots: dict[str, dict] = {}
        # 新規トピック検知用。None は起動直後で未初期化(この回では通知せず
        # 既存トピックをベースラインとして記録するだけにする)。
        self._known_topic_fqns: set[str] | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        # NOTE: テーブルチェック対象(SCHEDULED_TASK_TABLES)が未設定でも、
        # 新規トピック検知は常に有効にしたいためスレッド自体は起動する。
        if not self._table_fqns:
            log.warning("scheduled_task_tables_not_configured", reason="SCHEDULED_TASK_TABLES not configured")
        self._loop = loop
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
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

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._check_all_tables()
            self._check_new_topics()
            self._stop_event.wait(self._interval_seconds)

    def _check_new_topics(self) -> None:
        """OpenMetadata 上の全トピックを定期的に取得し、前回チェック時には
        無かった FQN があれば「新規トピックを検知」として通知する。
        (Kafka ブローカー自体をポーリングするのではなく、OpenMetadata に
        登録されたメタデータの増分を見る。register_topic_metadata ツールで
        登録した直後や、外部の ingestion パイプラインが取り込んだ直後に
        この定期チェックで拾われる。)"""
        try:
            client = get_openmetadata_client()
            topics = client.search_assets(query="*", asset_type="topic", limit=200)
            current_fqns = {t.get("fullyQualifiedName", "") for t in topics if t.get("fullyQualifiedName")}
        except Exception as e:
            log.error("scheduled_task_topic_check_failed", error=str(e))
            self._emit(self._make_topic_record("(全体)", "error", f"トピック一覧の取得に失敗しました: {e}"))
            return

        if self._known_topic_fqns is None:
            self._known_topic_fqns = current_fqns
            self._emit(self._make_topic_record(
                "(全体)", "ok", f"初回チェック: 既存トピック {len(current_fqns)} 件をベースラインとして記録"
            ))
            return

        new_fqns = current_fqns - self._known_topic_fqns
        self._known_topic_fqns = current_fqns
        for fqn in sorted(new_fqns):
            self._emit(self._make_topic_record(fqn, "changed", f"新しいトピックを検知: {fqn}"))

    def _make_topic_record(self, fqn: str, status: str, message: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "task_name": "openmetadata_new_topic_check",
            "fqn": fqn,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _check_all_tables(self) -> None:
        for fqn in self._table_fqns:
            try:
                record = self._check_table(fqn)
            except Exception as e:
                log.error("scheduled_task_check_failed", fqn=fqn, error=str(e))
                record = self._make_record(fqn, "error", f"チェック中にエラーが発生しました: {e}")
            self._emit(record)

    def _check_table(self, fqn: str) -> dict:
        client = get_openmetadata_client()
        table = client.get_table(fqn)
        if not table:
            return self._make_record(fqn, "error", f"テーブルが見つかりません: {fqn}")

        columns = len(table.get("columns", []))
        test_suite = table.get("testSuite", {}) or {}
        summary = test_suite.get("summary", {}) if test_suite else {}
        total = summary.get("total", 0)
        quality_score = (summary.get("success", 0) / total * 100) if total else None

        previous = self._snapshots.get(fqn)
        self._snapshots[fqn] = {"columns": columns, "qualityScore": quality_score}

        if previous is None:
            return self._make_record(
                fqn, "ok",
                f"初回チェック: カラム数={columns}"
                + (f", 品質スコア={quality_score:.1f}" if quality_score is not None else ""),
            )

        changes = []
        if previous["columns"] != columns:
            changes.append(f"カラム数 {previous['columns']} → {columns}")
        if (
            previous["qualityScore"] is not None
            and quality_score is not None
            and abs(previous["qualityScore"] - quality_score) >= 0.01
        ):
            changes.append(f"品質スコア {previous['qualityScore']:.1f} → {quality_score:.1f}")

        if changes:
            return self._make_record(fqn, "changed", "変更を検知: " + " / ".join(changes))
        return self._make_record(fqn, "ok", "変更なし")

    def _make_record(self, fqn: str, status: str, message: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "task_name": "openmetadata_schema_quality_check",
            "fqn": fqn,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _emit(self, record: dict) -> None:
        self._recent.append(record)
        log.info("scheduled_task_executed", **record)
        if self._loop is None:
            return
        for queue in list(self._subscribers):
            self._loop.call_soon_threadsafe(queue.put_nowait, record)


_bridge: ScheduledTaskBridge | None = None


def get_bridge() -> ScheduledTaskBridge:
    global _bridge
    if _bridge is None:
        tables = [
            t.strip()
            for t in os.environ.get("SCHEDULED_TASK_TABLES", "").split(",")
            if t.strip()
        ]
        _bridge = ScheduledTaskBridge(
            table_fqns=tables,
            interval_seconds=int(os.environ.get("SCHEDULED_TASK_INTERVAL_SECONDS", "300")),
        )
    return _bridge
