import asyncio
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import structlog

from tools.common.client import get_openmetadata_client
from tools.common.settings_store import get_settings_store
from tools.kafka.admin_tools import (
    _SITE_BOOTSTRAP_SERVERS,
    list_broker_topics,
    list_managed_kafka_topics,
)

log = structlog.get_logger()

_RECENT_MAXLEN = 50

# デフォルト値(設定ストアに保存された値が優先される)。
# 実ブローカーへの接続に連続で失敗した場合、以降は毎回(10分おき)ではなく
# 1時間おきにしかリトライしない(無駄な接続試行・ログ・通知を抑える)。
_DEFAULT_INTERVAL_SECONDS = 600
_DEFAULT_BACKOFF_FAILURE_THRESHOLD = 5
_DEFAULT_BACKOFF_INTERVAL_SECONDS = 3600


class ScheduledTaskBridge:
    """OpenMetadataのデータ品質・スキーマ変更を定期チェックし、SSE購読者へ配信する。

    Kafkaのような外部イベント源ではなく、Agent自身がバックグラウンドスレッドで
    一定間隔ごとにOpenMetadataへ問い合わせて前回結果と比較する、自発的な定期実行タスク。
    """

    def __init__(self, table_fqns: list[str], interval_seconds: int):
        self._table_fqns = table_fqns
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
        # サイトごとの実ブローカー接続の連続失敗回数とバックオフ用の最終チェック時刻
        self._broker_failure_counts: dict[str, int] = {}
        self._broker_last_checked: dict[str, float] = {}
        # GitHub organization への接続を初回利用時に一度だけ履歴パネルへ通知する
        self._github_notified = False

        # 設定画面から変更可能な値。設定ストアに保存された値があればそれを使う。
        store = get_settings_store()
        self._interval_seconds = int(
            (store.get("scheduled_task_interval_seconds") if store else None) or interval_seconds
        )
        self._backoff_failure_threshold = int(
            (store.get("scheduled_task_backoff_failure_threshold") if store else None)
            or _DEFAULT_BACKOFF_FAILURE_THRESHOLD
        )
        self._backoff_interval_seconds = int(
            (store.get("scheduled_task_backoff_interval_seconds") if store else None)
            or _DEFAULT_BACKOFF_INTERVAL_SECONDS
        )
        # 定期実行そのものの有効/無効(設定画面から停止・再開できるようにする)。
        # バックグラウンドスレッド自体は常に起動したままにし(interval変更等と
        # 同様、再起動なしで反映するため)、無効時は各チェック処理をスキップして
        # 次の間隔までスリープするだけにする。
        stored_enabled = store.get("scheduled_task_enabled") if store else None
        self._enabled = stored_enabled != "false"

    def get_settings(self) -> dict:
        return {
            "enabled": self._enabled,
            "interval_seconds": self._interval_seconds,
            "backoff_failure_threshold": self._backoff_failure_threshold,
            "backoff_interval_seconds": self._backoff_interval_seconds,
        }

    def update_settings(
        self,
        enabled: bool | None = None,
        interval_seconds: int | None = None,
        backoff_failure_threshold: int | None = None,
        backoff_interval_seconds: int | None = None,
    ) -> dict:
        store = get_settings_store()
        if enabled is not None:
            self._enabled = enabled
            if store:
                store.set("scheduled_task_enabled", "true" if enabled else "false")
        if interval_seconds is not None:
            self._interval_seconds = interval_seconds
            if store:
                store.set("scheduled_task_interval_seconds", str(interval_seconds))
        if backoff_failure_threshold is not None:
            self._backoff_failure_threshold = backoff_failure_threshold
            if store:
                store.set("scheduled_task_backoff_failure_threshold", str(backoff_failure_threshold))
        if backoff_interval_seconds is not None:
            self._backoff_interval_seconds = backoff_interval_seconds
            if store:
                store.set("scheduled_task_backoff_interval_seconds", str(backoff_interval_seconds))
        return self.get_settings()

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
            self._refresh_enabled_from_store()
            if self._enabled:
                self._check_all_tables()
                self._check_new_topics()
                self._check_broker_topics()
            self._stop_event.wait(self._interval_seconds)

    def _refresh_enabled_from_store(self) -> None:
        """設定ストアの enabled 値をループの各サイクルで読み直す。
        複数レプリカ構成では、設定画面のトグルはリクエストを受けた1台
        のみの self._enabled を即時反映するため、それ以外のレプリカは
        DBへの保存だけを頼りにここで反映する必要がある。"""
        store = get_settings_store()
        if not store:
            return
        try:
            stored_enabled = store.get("scheduled_task_enabled")
        except Exception as e:
            log.error("scheduled_task_settings_refresh_failed", error=str(e))
            return
        if stored_enabled is not None:
            self._enabled = stored_enabled != "false"

    def _check_broker_topics(self) -> None:
        """各サイトの実 Kafka ブローカーのトピック一覧を取得し、
        OpenMetadata に未登録のものがあれば register_topic_metadata で
        自動登録する。(create_kafka_topic のような書き込みではなく、
        list_topics() のみを使う読み取り専用チェック。ブローカー自体は
        変更しない。)"""
        try:
            om_client = get_openmetadata_client()
            om_topics = om_client.search_assets(query="*", asset_type="topic", limit=200)
            om_fqns = {t.get("fullyQualifiedName", "") for t in om_topics if t.get("fullyQualifiedName")}
        except Exception as e:
            log.error("scheduled_task_broker_check_om_fetch_failed", error=str(e))
            return

        now = time.monotonic()
        # NOTE: 1回のチェックサイクルで複数の未登録トピックが見つかることが
        # 多く(MM2ミラーコピーがまとめて未登録のまま溜まっていた場合等)、
        # 以前はトピックごとに履歴パネル/通知を1件ずつ出していたため、
        # 同じタイミングで大量の通知が並んでしまっていた。1サイクル分の
        # 結果をここに集約し、最後にまとめて1件だけ出す。
        discovered: list[dict] = []
        for service_name, bootstrap in _SITE_BOOTSTRAP_SERVERS.items():
            failures = self._broker_failure_counts.get(service_name, 0)
            last_checked = self._broker_last_checked.get(service_name)
            if (
                failures >= self._backoff_failure_threshold
                and last_checked is not None
                and (now - last_checked) < self._backoff_interval_seconds
            ):
                continue  # バックオフ中(設定した間隔が経過するまで再試行しない)

            self._broker_last_checked[service_name] = now
            try:
                broker_topic_names = list_broker_topics(bootstrap)
            except Exception as e:
                self._broker_failure_counts[service_name] = failures + 1
                self._notify_broker_connection_error(service_name, e)
                continue

            self._broker_failure_counts[service_name] = 0

            # 通知・自動登録の対象は Managed (Strimzi KafkaTopic CR 管理下) の
            # トピックのみに絞る。CLI直接作成の非Managedトピックは対象外。
            managed_result = list_managed_kafka_topics.invoke({"service_name": service_name})
            if not managed_result.get("success"):
                log.warning(
                    "scheduled_task_managed_topics_unavailable",
                    service_name=service_name, error=managed_result.get("error"),
                )
                continue
            managed_names = {t["topic_name"] for t in managed_result.get("topics", [])}

            for topic_name in sorted(broker_topic_names):
                if topic_name not in managed_names:
                    continue
                fqn = f"{service_name}.{topic_name}"
                if fqn in om_fqns:
                    continue
                discovered.append(self._register_discovered_topic(service_name, topic_name, fqn))

        if discovered:
            self._emit_discovered_topics_summary(discovered)

    def _notify_broker_connection_error(self, service_name: str, error: Exception) -> None:
        """実ブローカーへの接続エラーは頻発しがち(Skupperリンク切断時など)で、
        定期チェック実行履歴パネルに出すとノイズになるため通知ベルのみに出す
        (履歴パネル用の _recent には追加しない)。"""
        from agent.orchestrator.notifications import (
            get_bridge as get_notification_bridge,
        )
        log.error("scheduled_task_broker_check_failed", service_name=service_name, error=str(error))
        try:
            get_notification_bridge().push({
                "pipeline": "kafka_broker_topic_scan",
                "status": "ERROR",
                "message": f"[定期チェック] ({service_name}): 実ブローカーへの接続に失敗しました: {error}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            log.error("scheduled_task_notify_error_failed", error=str(e))

    def _register_discovered_topic(self, service_name: str, topic_name: str, fqn: str) -> dict:
        """検知した1トピックの登録結果を返す(履歴パネルへの emit はここでは行わず、
        _check_broker_topics 側で1サイクル分まとめて1件の通知にする)。"""
        from tools.openmetadata.schema_tools import register_topic_metadata

        description, source_note = self._enrich_topic_description(topic_name)

        try:
            result = register_topic_metadata.invoke({
                "topic_name": topic_name,
                "service_name": service_name,
                "description": description,
            })
        except Exception as e:
            return {"fqn": fqn, "success": False, "message": f"自動登録に失敗しました: {e}"}

        if result.get("success"):
            message = fqn if not source_note else f"{fqn} ({source_note})"
            return {"fqn": fqn, "success": True, "message": message}
        return {"fqn": fqn, "success": False, "message": f"自動登録に失敗しました: {result.get('error')}"}

    def _emit_discovered_topics_summary(self, discovered: list[dict]) -> None:
        """1チェックサイクル分の新規トピック検知結果をまとめて1件の
        履歴パネル項目(必要なら通知ベルにも)として出す。"""
        succeeded = [d for d in discovered if d["success"]]
        failed = [d for d in discovered if not d["success"]]

        lines = []
        if succeeded:
            lines.append(
                f"実ブローカーで新規トピックを{len(succeeded)}件検知し、OpenMetadataへ自動登録しました: "
                + ", ".join(d["message"] for d in succeeded)
            )
        if failed:
            lines.append(
                f"{len(failed)}件は自動登録に失敗しました: "
                + "; ".join(f"{d['fqn']} ({d['message']})" for d in failed)
            )

        status = "changed" if succeeded else "error"
        self._emit(self._make_topic_record(
            f"({len(discovered)}件)", status, "\n".join(lines), task_name="kafka_broker_topic_scan",
        ))

    def _enrich_topic_description(self, topic_name: str) -> tuple[str, str]:
        """GitHub organization 内のソースコードから、トピック名に対応する
        Entity/イベントクラスを探し、そのクラスコメントを説明文として使う。
        (Code Search API はこの組織のリポジトリではインデックス遅延により
        機能しないため、リポジトリのファイルツリーを取得してファイル名で
        絞り込む find_github_files_by_name を使う。)
        見つからない場合は汎用の説明文にフォールバックする。"""
        fallback = "(自動検知・自動登録) 実ブローカー上に存在するがOpenMetadata未登録だったトピック"
        if not self._github_notified:
            self._github_notified = True
            self._emit(self._make_topic_record(
                "(GitHub)", "ok",
                f"ソースコードからのメタ情報推定のため GitHub organization "
                f"'{os.environ.get('GITHUB_ORG', 'quarkusdroneshop')}' に接続します(読み取りのみ)",
                task_name="kafka_broker_topic_scan",
            ))
        if not os.environ.get("GITHUB_TOKEN"):
            return fallback, ""

        keyword = "".join(part.capitalize() for part in topic_name.replace("_", "-").split("-"))
        try:
            from tools.github.github_tools import (
                find_github_files_by_name,
                get_github_file_content,
                list_github_org_repos,
            )

            repos_result = list_github_org_repos.invoke({})
            if not repos_result.get("success"):
                return fallback, ""

            for repo in repos_result.get("repos", []):
                repo_name = repo["name"]
                files_result = find_github_files_by_name.invoke({"repo": repo_name, "name_keyword": keyword})
                if not files_result.get("success") or not files_result.get("paths"):
                    continue
                path = files_result["paths"][0]
                content_result = get_github_file_content.invoke({"repo": repo_name, "path": path})
                if not content_result.get("success"):
                    continue
                comment = self._extract_class_comment(content_result.get("content", ""))
                if comment:
                    org = os.environ.get("GITHUB_ORG", "quarkusdroneshop")
                    github_url = f"https://github.com/{org}/{repo_name}/blob/main/{path}"
                    return comment, f"出典: [{repo_name}/{path}]({github_url})"
        except Exception as e:
            log.error("topic_enrichment_failed", topic_name=topic_name, error=str(e))
        return fallback, ""

    @staticmethod
    def _extract_class_comment(source: str) -> str:
        """Javaソースの先頭付近にある /** ... */ 形式のクラスコメントを
        抜き出す(素朴な実装。厳密なパースは行わない)。"""
        import re
        match = re.search(r"/\*\*(.*?)\*/", source, re.DOTALL)
        if not match:
            return ""
        lines = [
            line.strip().lstrip("*").strip()
            for line in match.group(1).splitlines()
            if line.strip().lstrip("*").strip()
        ]
        comment = " ".join(lines)[:300]
        return comment

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

    def _make_topic_record(
        self, fqn: str, status: str, message: str,
        task_name: str = "openmetadata_topic_registry_check",
    ) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "task_name": task_name,
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
        if record.get("status") == "error":
            self._notify_error(record)
        if self._loop is None:
            return
        for queue in list(self._subscribers):
            self._loop.call_soon_threadsafe(queue.put_nowait, record)

    def _notify_error(self, record: dict) -> None:
        """定期チェックのエラーは実行履歴パネルだけでなく通知ベルにも
        表示する(見落としを防ぐため)。"""
        from agent.orchestrator.notifications import (
            get_bridge as get_notification_bridge,
        )
        try:
            get_notification_bridge().push({
                "pipeline": record.get("task_name", "scheduled_task"),
                "status": "ERROR",
                "message": f"[定期チェック] {record.get('fqn', '')}: {record.get('message', '')}",
                "timestamp": record.get("timestamp", ""),
            })
        except Exception as e:
            log.error("scheduled_task_notify_error_failed", error=str(e))


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
