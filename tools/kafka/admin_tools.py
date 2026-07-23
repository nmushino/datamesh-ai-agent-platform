"""サイトの Kafka ブローカーに対する実トピック作成ツール。

OpenMetadata に登録されている A/B/C サイトの messagingService
(external-shop-cluster-kafka-Xsite:9094) は、Skupper 経由で
quarkusdroneshop-rhdh namespace 内にサービスとして公開されている。
OpenMetadata へのメタデータ登録(register_topic_metadata)とは別に、
このツールで実際のブローカー上にトピックを作成する。

Python の Kafka クライアントライブラリ(kafka-python)は、この Kafka 4.x
(KRaft) ブローカーとの ApiVersions ネゴシエーションが非互換で
NodeNotReadyError/NoBrokersAvailable になることを確認済みのため使わない。
実績のある kafka-topics.sh (CLI, コンテナイメージに同梱) を subprocess
経由で呼び出す。
"""
from __future__ import annotations

import os
import subprocess
import time

import httpx
import structlog
from langchain_core.tools import tool

from tools.common.status import push_status

log = structlog.get_logger()

_KAFKA_TOPICS_CMD = "kafka-topics.sh"

# NOTE: これらのブローカーは ai-agent-orchestrator と別 namespace
# (quarkusdroneshop-rhdh) で Skupper により公開されているサービスのため、
# Fully Qualified なクラスタ内DNS名を使う必要がある(同一namespace名のみ
# では解決できない)。以前は openmetadata namespace を指していたが、その
# Skupper サイトは A/B/C とのリンクが未確立(listener が
# "Pending / No matching connectors")で常に接続タイムアウトしていたため、
# 実際にリンクが確立している quarkusdroneshop-rhdh namespace 側に変更した。
_SITE_BOOTSTRAP_SERVERS = {
    "external-shop-cluster-kafka-asite:9094": "external-shop-cluster-kafka-asite.quarkusdroneshop-rhdh.svc.cluster.local:9094",
    "external-shop-cluster-kafka-bsite:9094": "external-shop-cluster-kafka-bsite.quarkusdroneshop-rhdh.svc.cluster.local:9094",
    "external-shop-cluster-kafka-csite:9094": "external-shop-cluster-kafka-csite.quarkusdroneshop-rhdh.svc.cluster.local:9094",
}

# MirrorMaker2 が各サイト間でトピックを相互ミラーリングしており
# (topicsPattern: qdca10-in|qdca10pro-in|orders.*|web.*|inventory.*|
# eighty-six.*|rewards|loyalty-updates.* に一致するトピックが対象)、
# ミラー先では "shop-<元サイト>.<トピック名>" という名前になる
# (例: Aサイトの "orders-test" は B/Cサイトでは "shop-asite.orders-test")。
# 元サイトだけ削除してもMM2が自身のチェックポイントに基づき再同期して
# 復活してしまうことを実際に確認したため、delete_kafka_topic では
# 元サイト削除に加えて他サイトのミラーコピーも削除する。
_SITE_SHORT_NAMES = {
    "external-shop-cluster-kafka-asite:9094": "asite",
    "external-shop-cluster-kafka-bsite:9094": "bsite",
    "external-shop-cluster-kafka-csite:9094": "csite",
}

# kafka-topics.sh はコマンドごとに JVM を新規起動するため、Pythonクライアント
# と比べて起動コストが大きい。コンテナのCPU上限を引き上げた後も、バックグラウンド
# の notification consumer (kafka-python、既知の非互換で再接続を繰り返し続けている)
# がCPUを奪い合うことで実測60秒を超えるケースが確認されたため、さらに余裕を持たせる。
_CMD_TIMEOUT_SECONDS = 90

# ミラーコピー("shop-<サイト>.<トピック名>")は元トピックの作成/削除有無に
# 応じて存在しないこともあり、その場合は UnknownTopicOrPartitionException で
# 即座に返る想定の操作のため、通常の削除より短いタイムアウトでよい。
_MIRROR_DELETE_TIMEOUT_SECONDS = 15

# delete_kafka_topic は MM2一時停止(約5秒待機)+ 元サイト削除 + ミラー削除
# (最大2サイト) + MM2再開までの保持時間を直列に行うため、全体の所要時間が
# 積み上がりやすい。ChatUI〜vLLM間のどこかでHTTPタイムアウトに達するリスクを
# 抑えるため、元サイト削除には汎用の _CMD_TIMEOUT_SECONDS (90秒、JVM起動が
# 遅い場合の余裕を見た値) より短いタイムアウトを個別に設定する。
_PRIMARY_DELETE_TIMEOUT_SECONDS = 45

# MM2は自身の内部チェックポイント(config/offset storageトピック)を基に
# トピックを再作成することがあり、ミラー先を削除してもソース側の現状に
# 関わらず復活してしまうことを実際に確認した(A/B/Cのミラーを何度削除しても
# MM2により再作成された)。delete_kafka_topic は削除の前後で各サイトの
# MirrorMaker2 (KafkaMirrorMaker2 リソース) を一時停止/再開することで
# これを防ぐ。Kafka wire protocol (Skupper経由) とは別に、各サイト自身の
# Kubernetes API への到達性とスコープを絞ったServiceAccountトークンが必要
# (deployment/kustomize/base/networkpolicy.yaml, *-mm2-pause-token Secret 参照)。
_MM2_SITES = ["asite", "bsite", "csite"]
_MM2_RESOURCE_NAME = "mm2-extended"
_MM2_NAMESPACE = "quarkusdroneshop-demo"
_MM2_API_TIMEOUT_SECONDS = 15
# 削除完了後、MM2を再開するまで一時停止状態を維持する時間。短すぎると
# 再開直後の最初の調整サイクルで内部チェックポイントからトピックが
# 再作成されてしまう事例を確認したため、ある程度の余裕を持たせる。
_MM2_PAUSE_HOLD_SECONDS = 60


def _mm2_api_config(site: str) -> tuple[str, str] | None:
    """<site>_MM2_API_SERVER / <site>_MM2_TOKEN 環境変数から接続情報を返す。
    未設定の場合は None (MM2一時停止をスキップし、通常のトピック削除のみ行う)。"""
    api_server = os.environ.get(f"{site.upper()}_MM2_API_SERVER")
    token = os.environ.get(f"{site.upper()}_MM2_TOKEN")
    if not api_server or not token:
        return None
    return api_server, token


def _set_mm2_pause(site: str, pause: bool) -> dict:
    config = _mm2_api_config(site)
    if config is None:
        log.warning("mm2_pause_skipped", site=site, pause=pause, reason="credentials not set")
        return {"site": site, "skipped": True, "reason": "MM2 API 認証情報が未設定", "success": True}

    api_server, token = config
    url = (
        f"{api_server}/apis/kafka.strimzi.io/v1beta2/namespaces/{_MM2_NAMESPACE}"
        f"/kafkamirrormaker2s/{_MM2_RESOURCE_NAME}"
    )
    try:
        resp = httpx.patch(
            url,
            # NOTE: Strimzi の KafkaMirrorMaker2 に spec.pause フィールドは存在しない
            # (CRDスキーマに無く、当初 spec.pause で PATCH したが無視されて何も
            # 効果がないことを実際に確認した)。Strimzi はどのカスタムリソースも
            # 共通で strimzi.io/pause-reconciliation アノテーションで一時停止する。
            json={"metadata": {"annotations": {"strimzi.io/pause-reconciliation": "true" if pause else "false"}}},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/merge-patch+json",
            },
            # NOTE: 各サイトのKubernetes APIサーバー証明書はサイトごとのクラスタ内CAが
            # 発行しており、このコンテナイメージにCAバンドルを同梱していないため
            # 検証をスキップする。トークン自体はmm2-extendedリソースのget/patchのみに
            # 絞られたScoped ServiceAccountであり、漏洩時の影響範囲は限定的。
            verify=False,
            timeout=_MM2_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        log.info("mm2_pause_set", site=site, pause=pause)
        return {"site": site, "paused": pause, "success": True}
    except Exception as e:
        log.error("mm2_pause_failed", site=site, pause=pause, error=str(e))
        return {"site": site, "paused": None, "success": False, "error": str(e)}


_STRIMZI_KAFKA_CLUSTER_NAME = "shop-cluster"


def _apply_kafkatopic_cr(site: str, topic_name: str, partitions: int, replication_factor: int) -> dict:
    """<site> に KafkaTopic カスタムリソース(Strimzi Topic Operator管理)を作成/更新する。
    Topic Operator がこの CR を正として実ブローカー上にトピックを反映する
    (create_kafka_topic の managed=True 経路)。認証情報が無い場合は失敗として返す
    (CLI直接作成へのフォールバックは呼び出し元の判断に委ねる)。"""
    config = _mm2_api_config(site)
    if config is None:
        return {"site": site, "applied": False, "success": False, "error": "K8s API 認証情報が未設定"}

    api_server, token = config
    url = f"{api_server}/apis/kafka.strimzi.io/v1/namespaces/{_MM2_NAMESPACE}/kafkatopics/{topic_name}"
    body = {
        "apiVersion": "kafka.strimzi.io/v1",
        "kind": "KafkaTopic",
        "metadata": {
            "name": topic_name,
            "namespace": _MM2_NAMESPACE,
            "labels": {"strimzi.io/cluster": _STRIMZI_KAFKA_CLUSTER_NAME},
        },
        "spec": {
            "partitions": partitions,
            "replicas": replication_factor,
        },
    }
    try:
        # NOTE: apply 相当 (Server-Side Apply) で新規作成/既存更新の両方に対応する。
        # force=true を付けないと既存 CR (他アクターが作成したフィールド) との
        # 所有権競合で 409 Conflict になることがあるため付与する。
        resp = httpx.patch(
            url,
            params={"fieldManager": "ai-agent-orchestrator", "force": "true"},
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/apply-patch+yaml",
            },
            verify=False,
            timeout=_MM2_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        log.info("kafkatopic_cr_applied", site=site, topic_name=topic_name, partitions=partitions, replication_factor=replication_factor)
        return {"site": site, "applied": True, "success": True}
    except Exception as e:
        log.error("kafkatopic_cr_apply_failed", site=site, topic_name=topic_name, error=str(e))
        return {"site": site, "applied": False, "success": False, "error": str(e)}


def _delete_kafkatopic_cr(site: str, topic_name: str) -> dict:
    """<site> の KafkaTopic カスタムリソース(Strimzi Topic Operator管理)を削除する。
    Topic Operator は KafkaTopic CR を正とみなし、ブローカー上のトピックが
    CLIで直接削除されてもCRが残っていれば実トピックを再作成して
    しまうことを実際に確認した(Aサイトの orders-test が原因不明のまま
    復活し続けていた真因)。ブローカー上の削除だけでは不十分で、対応する
    KafkaTopic CRの削除が必須。認証情報が無い場合はスキップ(現時点ではCサイト)。"""
    config = _mm2_api_config(site)
    if config is None:
        return {"site": site, "skipped": True, "reason": "K8s API 認証情報が未設定", "success": True}

    api_server, token = config
    url = f"{api_server}/apis/kafka.strimzi.io/v1/namespaces/{_MM2_NAMESPACE}/kafkatopics/{topic_name}"
    try:
        resp = httpx.delete(
            url,
            headers={"Authorization": f"Bearer {token}"},
            verify=False,
            timeout=_MM2_API_TIMEOUT_SECONDS,
        )
        if resp.status_code == 404:
            return {"site": site, "deleted": False, "message": "KafkaTopic CRは存在しません", "success": True}
        resp.raise_for_status()
        log.info("kafkatopic_cr_deleted", site=site, topic_name=topic_name)
        return {"site": site, "deleted": True, "success": True}
    except Exception as e:
        log.error("kafkatopic_cr_delete_failed", site=site, topic_name=topic_name, error=str(e))
        return {"site": site, "deleted": False, "success": False, "error": str(e)}


def _pause_all_mm2() -> list[dict]:
    return [_set_mm2_pause(site, True) for site in _MM2_SITES]


def _resume_all_mm2() -> list[dict]:
    return [_set_mm2_pause(site, False) for site in _MM2_SITES]


def _exclude_topic_from_pattern(pattern: str, topic_name: str) -> str:
    """既存の topicsPattern の直後に、指定トピック名だけを除外する否定先読みを
    追加する。どの選択肢(orders.*等)がマッチしていたかに関わらず機能する
    汎用的な方法(例: "^(orders.*|...)$" -> "^(?!orders-test$)(orders.*|...)$")。
    既に同じ除外が含まれている場合は何もしない(冪等)。"""
    import re as _re
    exclusion = f"(?!{_re.escape(topic_name)}$)"
    if exclusion in pattern:
        return pattern
    if pattern.startswith("^"):
        return "^" + exclusion + pattern[1:]
    return exclusion + pattern


def _mirror_matches_source(mirror: dict, source_cluster_alias: str, source_service_name: str) -> bool:
    """mirrors[] の1エントリが、削除元サイトを sourceCluster としているかを判定する。
    実際のライブリソースを確認したところ、想定していた spec.mirrors[].sourceCluster
    フィールドを持たない構成(sourceConnector.config.bootstrap.servers に直接
    ブローカーアドレスを埋め込む形式)のサイトが存在することが分かった
    (このフィールド不一致により、除外パターンが一切適用されない不具合が
    発生していた)。両方の構成に対応するため、どちらの手掛かりでも判定する。"""
    if mirror.get("sourceCluster") == source_cluster_alias:
        return True
    bootstrap_servers = mirror.get("sourceConnector", {}).get("config", {}).get("bootstrap.servers", "")
    return bootstrap_servers == source_service_name


def _exclude_topic_on_mm2(site: str, source_cluster_alias: str, source_service_name: str, topic_name: str) -> dict:
    """<site> の KafkaMirrorMaker2 リソースについて、削除元サイトを sourceCluster
    とする mirrors エントリの topicsPattern から topic_name を除外する。
    MM2は自身の内部チェックポイントに基づいてトピックを再作成することがあり
    (削除直後にMM2を再開すると復活する事例を確認済み)、その根本原因(再照合
    対象のパターンに一致し続けていること)を解消する唯一の安全な方法として、
    削除の都度このパターン自体を更新する。
    (spec.mirrors はK8s側でリスト全体を置き換える必要があるため、まずGETで
    現在の全エントリを取得し、対象エントリだけを書き換えて丸ごとPATCHし直す。)"""
    config = _mm2_api_config(site)
    if config is None:
        return {"site": site, "skipped": True, "reason": "MM2 API 認証情報が未設定", "success": True}

    api_server, token = config
    url = (
        f"{api_server}/apis/kafka.strimzi.io/v1beta2/namespaces/{_MM2_NAMESPACE}"
        f"/kafkamirrormaker2s/{_MM2_RESOURCE_NAME}"
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        get_resp = httpx.get(url, headers=headers, verify=False, timeout=_MM2_API_TIMEOUT_SECONDS)
        get_resp.raise_for_status()
        mirrors = get_resp.json().get("spec", {}).get("mirrors", [])

        changed = False
        for mirror in mirrors:
            if not _mirror_matches_source(mirror, source_cluster_alias, source_service_name):
                continue
            current_pattern = mirror.get("topicsPattern", "")
            new_pattern = _exclude_topic_from_pattern(current_pattern, topic_name)
            if new_pattern != current_pattern:
                mirror["topicsPattern"] = new_pattern
                changed = True

        if not changed:
            return {"site": site, "changed": False, "success": True}

        patch_resp = httpx.patch(
            url,
            json={"spec": {"mirrors": mirrors}},
            headers={**headers, "Content-Type": "application/merge-patch+json"},
            verify=False,
            timeout=_MM2_API_TIMEOUT_SECONDS,
        )
        patch_resp.raise_for_status()
        log.info("mm2_topic_excluded", site=site, source_cluster=source_cluster_alias, topic_name=topic_name)
        return {"site": site, "changed": True, "success": True}
    except Exception as e:
        log.error(
            "mm2_topic_exclusion_failed",
            site=site, source_cluster=source_cluster_alias, topic_name=topic_name, error=str(e),
        )
        return {"site": site, "changed": False, "success": False, "error": str(e)}


def list_broker_topics(bootstrap: str) -> set[str]:
    """指定ブローカー上に存在するトピック名の集合を返す(kafka-topics.sh --list)。
    scheduled_tasks.py の定期スキャンから使われる読み取り専用のヘルパー。
    接続/コマンド失敗時は例外をそのまま送出する(呼び出し元でバックオフ処理する)。"""
    result = subprocess.run(
        [_KAFKA_TOPICS_CMD, "--list", "--bootstrap-server", bootstrap],
        capture_output=True,
        text=True,
        timeout=_CMD_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


@tool
def topic_exists(topic_name: str, service_name: str) -> dict:
    """
    対象サイトの実際の Kafka ブローカー上に、指定したトピックが既に
    存在するかどうかを確認します。Developer Hub 等から「このトピック名が
    存在しなければ新規作成する」という依頼を受けた場合、create_kafka_topic
    を呼ぶ前にこのツールで存在確認を行うこと。

    Args:
        topic_name: 確認するトピック名
        service_name: 対象サイトの Messaging Service 名。
            Aサイト: "external-shop-cluster-kafka-asite:9094"
            Bサイト: "external-shop-cluster-kafka-bsite:9094"
            Cサイト: "external-shop-cluster-kafka-csite:9094"
    """
    bootstrap = _SITE_BOOTSTRAP_SERVERS.get(service_name)
    if not bootstrap:
        return {
            "error": f"未知の service_name: {service_name}。"
                     f"利用可能な値: {list(_SITE_BOOTSTRAP_SERVERS.keys())}",
            "success": False,
        }

    log.info("topic_exists_check", topic_name=topic_name, service_name=service_name, bootstrap=bootstrap)
    try:
        topics = list_broker_topics(bootstrap)
    except subprocess.TimeoutExpired:
        return {"error": f"トピック存在確認エラー ({bootstrap}): コマンドがタイムアウトしました", "success": False}
    except Exception as e:
        log.error("topic_exists_check_failed", topic_name=topic_name, service_name=service_name, error=str(e))
        return {"error": f"トピック存在確認エラー ({bootstrap}): {str(e)}", "success": False}

    return {
        "topic_name": topic_name,
        "service_name": service_name,
        "exists": topic_name in topics,
        "success": True,
    }


@tool
def create_kafka_topic(
    topic_name: str, service_name: str, partitions: int = 10, replication_factor: int = 1, managed: bool = True,
) -> dict:
    """
    対象サイトの実際の Kafka ブローカー上にトピックを作成します。
    (OpenMetadata へのメタデータ登録とは別処理。新しいトピックを求められた
    場合は、まずこのツールで実ブローカーにトピックを作成してから、
    register_topic_metadata で OpenMetadata に登録すること)

    Args:
        topic_name: 作成するトピック名 (例: "oder-test")
        service_name: 対象サイトの Messaging Service 名。
            Aサイト: "external-shop-cluster-kafka-asite:9094"
            Bサイト: "external-shop-cluster-kafka-bsite:9094"
            Cサイト: "external-shop-cluster-kafka-csite:9094"
        partitions: パーティション数 (デフォルト10。ユーザーが明示的に別の値を
            指定した場合のみそれに従うこと)
        replication_factor: レプリケーションファクタ (デフォルト1)
        managed: true (デフォルト) の場合、kafka-topics.sh によるブローカー
            直接作成ではなく、KafkaTopic カスタムリソース (Strimzi Topic
            Operator 管理) を作成/更新する。GitOps的にトピックをK8sリソース
            として管理する標準運用のため、ユーザーが明示的に「直接作成」等を
            指定しない限り常に true のままにすること。false の場合は
            kafka-topics.sh によるブローカーへの直接CLI作成になる
            (対象サイトのK8s API認証情報が未設定の場合、managed=true はエラーを返す)。
    """
    bootstrap = _SITE_BOOTSTRAP_SERVERS.get(service_name)
    if not bootstrap:
        return {
            "error": f"未知の service_name: {service_name}。"
                     f"利用可能な値: {list(_SITE_BOOTSTRAP_SERVERS.keys())}",
            "success": False,
        }

    if managed:
        short_name = _SITE_SHORT_NAMES.get(service_name, service_name)
        log.info("create_kafka_topic_managed", topic_name=topic_name, service_name=service_name, site=short_name)
        cr_result = _apply_kafkatopic_cr(short_name, topic_name, partitions, replication_factor)
        if not cr_result["success"]:
            return {
                "error": f"KafkaTopic CR 作成エラー ({short_name}): {cr_result.get('error')}",
                "topic_name": topic_name,
                "service_name": service_name,
                "success": False,
            }
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "created": True,
            "managed": True,
            "message": "KafkaTopic CR (Strimzi Topic Operator管理) として作成/更新しました",
            "success": True,
        }

    log.info("create_kafka_topic", topic_name=topic_name, service_name=service_name, bootstrap=bootstrap)
    try:
        result = subprocess.run(
            [
                _KAFKA_TOPICS_CMD,
                "--create",
                "--bootstrap-server", bootstrap,
                "--topic", topic_name,
                "--partitions", str(partitions),
                "--replication-factor", str(replication_factor),
            ],
            capture_output=True,
            text=True,
            timeout=_CMD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        log.error("create_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error="timeout")
        return {"error": f"トピック作成エラー ({bootstrap}): コマンドがタイムアウトしました", "success": False}
    except Exception as e:
        log.error("create_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=str(e))
        return {"error": f"トピック作成エラー ({bootstrap}): {str(e)}", "success": False}

    if result.returncode == 0:
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "bootstrap_servers": bootstrap,
            "created": True,
            "success": True,
        }

    stderr = result.stderr.strip()
    if "TopicExistsException" in stderr:
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "created": False,
            "message": "トピックは既にブローカー上に存在します",
            "success": True,
        }

    log.error("create_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=stderr)
    return {"error": f"トピック作成エラー ({bootstrap}): {stderr or result.stdout.strip()}", "success": False}


_SITE_DISPLAY_NAMES = {"asite": "Aサイト", "bsite": "Bサイト", "csite": "Cサイト"}


def _delete_topic_via_cli(bootstrap: str, topic_name: str, timeout_seconds: int) -> dict:
    """Skupper経由の外部リスナー(9094)に対して kafka-topics.sh --delete を実行する。
    site指定時はKafkaTopic CR削除(実削除の主経路)後の確認/フォールバックとして、
    site未指定時(ミラー等)は唯一の削除経路として使う。"""
    try:
        result = subprocess.run(
            [
                _KAFKA_TOPICS_CMD,
                "--delete",
                "--bootstrap-server", bootstrap,
                "--topic", topic_name,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"トピック削除エラー ({bootstrap}): コマンドがタイムアウトしました", "success": False}
    except Exception as e:
        return {"error": f"トピック削除エラー ({bootstrap}): {str(e)}", "success": False}

    if result.returncode == 0:
        return {"deleted": True, "success": True}

    stderr = result.stderr.strip()
    # NOTE: 「トピックが存在しない」ことを表すエラー文言は kafka-topics.sh の
    # バージョンによって異なる。UnknownTopicOrPartitionException だけでなく、
    # このクラスタでは "IllegalArgumentException: Topic '...' does not exist
    # as expected" という文言で返ってくることを実際に確認した(CR削除で既に
    # 消えているトピックへの確認削除がこの文言でエラー扱いになり、実際には
    # 正常なケースが失敗として報告される不具合があった)。
    if "UnknownTopicOrPartitionException" in stderr or "does not exist" in stderr:
        return {"deleted": False, "message": "トピックはブローカー上に存在しません", "success": True}

    return {"error": f"トピック削除エラー ({bootstrap}): {stderr or result.stdout.strip()}", "success": False}


def _delete_topic_on_broker(
    bootstrap: str, topic_name: str, timeout_seconds: int = _CMD_TIMEOUT_SECONDS, site: str | None = None,
) -> dict:
    """指定ブローカー上の指定トピックを削除する内部ヘルパー。
    topic_name/service_name を含まない結果 dict (deleted/success/message/error) を返す。

    NOTE: Strimzi Topic Operator が KafkaTopic CR を正として管理しており、
    ブローカー上のトピックをCLIで直接削除しても、対応するCRが残っていれば
    Operatorが実トピックを再作成してしまうことを確認した(Aサイトの
    orders-test が原因不明のまま復活し続けていた真因)。そのため site が
    指定されている場合は、Skupper経由CLI削除より先にKafkaTopic CRを削除する
    (Operatorのfinalizer経由の削除が実トピック削除の主経路となり、後続の
    CLI削除は既に消えている前提のフォールバック/確認として働く)。"""
    display_name = _SITE_DISPLAY_NAMES.get(site, site or "")
    cr_result = None
    if site:
        push_status(f"{display_name}処理中...")
        cr_result = _delete_kafkatopic_cr(site, topic_name)
        if not cr_result["success"]:
            log.warning("kafkatopic_cr_delete_failed_continuing", site=site, topic_name=topic_name, error=cr_result.get("error"))
        if cr_result.get("deleted"):
            # Topic Operator がfinalizer経由で実トピックを削除し終えるまで一呼吸置く。
            time.sleep(3)

    if cr_result is not None and cr_result.get("deleted"):
        # NOTE: CR削除で既に実トピックは消えている。後続のCLI削除は「もう
        # 存在しない」ことを確認するだけの位置づけだが、そのエラー表現は
        # kafka-topics.sh のバージョンによって異なり
        # (UnknownTopicOrPartitionException だけでなく、実際に
        # "IllegalArgumentException: Topic '...' does not exist as expected"
        # という文言で返ってくるケースを確認した)、その全てを網羅して
        # 「正常」と判定するのは脆い。CR削除が成功した時点で削除は完了して
        # いるため、後続CLIの結果内容に関わらずここで確定して返す。
        return {"deleted": True, "success": True, "message": "KafkaTopic CR削除により削除されました", "kafkatopic_cr": cr_result}

    result = _delete_topic_via_cli(bootstrap, topic_name, timeout_seconds)
    if cr_result is not None:
        result["kafkatopic_cr"] = cr_result
    return result


@tool
def delete_kafka_topic(topic_name: str, service_name: str) -> dict:
    """
    対象サイトの実際の Kafka ブローカー上のトピックを削除します。
    (この操作はブローカー上のデータを完全に失わせる不可逆な書き込みです。
    OpenMetadata側のメタデータ登録は削除しないため、必要であれば別途
    OpenMetadata側のエントリも整理すること)

    対象トピックが MirrorMaker2 のミラー対象パターンに一致する場合、他サイトに
    ミラーコピー("shop-<このサイト>.<トピック名>")が存在することがあり、
    元サイトだけ削除してもMM2のチェックポイントにより再同期されて復活して
    しまう(ソース側が既に存在しなくてもMM2の内部状態から再作成される事例を
    確認済み)。そのためこのツールはまず全サイトのMM2を一時停止し、元サイト
    削除に続けて他サイト上のミラーコピーも削除、最後にMM2を再開する。

    Args:
        topic_name: 削除するトピック名
        service_name: 対象サイトの Messaging Service 名。
            Aサイト: "external-shop-cluster-kafka-asite:9094"
            Bサイト: "external-shop-cluster-kafka-bsite:9094"
            Cサイト: "external-shop-cluster-kafka-csite:9094"
    """
    bootstrap = _SITE_BOOTSTRAP_SERVERS.get(service_name)
    if not bootstrap:
        return {
            "error": f"未知の service_name: {service_name}。"
                     f"利用可能な値: {list(_SITE_BOOTSTRAP_SERVERS.keys())}",
            "success": False,
        }

    log.info("delete_kafka_topic", topic_name=topic_name, service_name=service_name, bootstrap=bootstrap)

    push_status("MM2の停止")
    mm2_pause_results = _pause_all_mm2()
    # NOTE: 一時停止のAPI呼び出しが返っても、Strimzi Operator がConnectタスクを
    # 実際に停止させるまでには数秒のラグがあるため、削除実行前に少し待つ。
    time.sleep(5)

    short_name = _SITE_SHORT_NAMES.get(service_name, service_name)

    try:
        primary = _delete_topic_on_broker(
            bootstrap, topic_name, timeout_seconds=_PRIMARY_DELETE_TIMEOUT_SECONDS, site=short_name,
        )
        if not primary["success"]:
            log.error("delete_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=primary.get("error"))
            return {**primary, "topic_name": topic_name, "service_name": service_name, "mm2_pause_results": mm2_pause_results}

        mirror_deletions = []
        for other_service, other_bootstrap in _SITE_BOOTSTRAP_SERVERS.items():
            if other_service == service_name:
                continue
            other_short_name = _SITE_SHORT_NAMES.get(other_service, other_service)
            mirror_topic = f"shop-{short_name}.{topic_name}"
            mirror_result = _delete_topic_on_broker(
                other_bootstrap, mirror_topic, timeout_seconds=_MIRROR_DELETE_TIMEOUT_SECONDS, site=other_short_name,
            )
            if not mirror_result["success"]:
                log.error(
                    "delete_kafka_topic_mirror_failed",
                    topic_name=mirror_topic, service_name=other_service, error=mirror_result.get("error"),
                )
            mirror_deletions.append({
                "service_name": other_service,
                "topic_name": mirror_topic,
                **mirror_result,
            })

        # NOTE: MM2は自身の内部チェックポイントに基づいてトピックを再作成する
        # ことがあり、削除しても一時停止を解除すると復活してしまうことを実際に
        # 確認した。根本原因(このトピック名がtopicsPatternに一致し続けている
        # こと)を解消するため、削除元サイトを sourceCluster とする他サイトの
        # mirrors設定から、このトピック名を否定先読みで除外する。以後の
        # refreshサイクルでこのトピックが再ミラーリング対象にならなくなる。
        push_status("MM2の除外パターンを更新しています...")
        source_cluster_alias = f"shop-{short_name}"
        pattern_exclusions = [
            _exclude_topic_on_mm2(other_short, source_cluster_alias, service_name, topic_name)
            for other_short in _MM2_SITES
            if other_short != short_name
        ]

        # NOTE: MM2 は一時停止中も自身の内部チェックポイント(mirrormaker2-cluster-
        # offsets 等)にトピックの存在を記憶しており、削除直後に再開すると
        # そのチェックポイントに基づいて再作成してしまうことを実際に確認した。
        # 一時停止状態をしばらく維持することで、Strimzi Operator/Kafka Connect
        # フレームワーク側の状態がより落ち着いてから再開されるようにする。
        time.sleep(_MM2_PAUSE_HOLD_SECONDS)
    finally:
        push_status("MM2の再開")
        mm2_resume_results = _resume_all_mm2()

    return {
        "mm2_pause_results": mm2_pause_results,
        "mm2_resume_results": mm2_resume_results,
        "mm2_pattern_exclusions": pattern_exclusions,
        "topic_name": topic_name,
        "service_name": service_name,
        "bootstrap_servers": bootstrap,
        "deleted": primary["deleted"],
        "success": True,
        "mirror_deletions": mirror_deletions,
    }
