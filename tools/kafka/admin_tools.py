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

import subprocess

import structlog
from langchain_core.tools import tool

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

# kafka-topics.sh はコマンドごとに JVM を新規起動するため、Pythonクライアント
# と比べて起動コストが大きい。コンテナのCPU制限(500m)下では実測で
# 40秒前後かかることを確認したため、それに対して十分な余裕を持たせる。
_CMD_TIMEOUT_SECONDS = 60


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
def create_kafka_topic(topic_name: str, service_name: str, partitions: int = 1, replication_factor: int = 1) -> dict:
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
        partitions: パーティション数 (デフォルト1)
        replication_factor: レプリケーションファクタ (デフォルト1)
    """
    bootstrap = _SITE_BOOTSTRAP_SERVERS.get(service_name)
    if not bootstrap:
        return {
            "error": f"未知の service_name: {service_name}。"
                     f"利用可能な値: {list(_SITE_BOOTSTRAP_SERVERS.keys())}",
            "success": False,
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


@tool
def delete_kafka_topic(topic_name: str, service_name: str) -> dict:
    """
    対象サイトの実際の Kafka ブローカー上のトピックを削除します。
    (この操作はブローカー上のデータを完全に失わせる不可逆な書き込みです。
    OpenMetadata側のメタデータ登録は削除しないため、必要であれば別途
    OpenMetadata側のエントリも整理すること)

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
            timeout=_CMD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        log.error("delete_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error="timeout")
        return {"error": f"トピック削除エラー ({bootstrap}): コマンドがタイムアウトしました", "success": False}
    except Exception as e:
        log.error("delete_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=str(e))
        return {"error": f"トピック削除エラー ({bootstrap}): {str(e)}", "success": False}

    if result.returncode == 0:
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "bootstrap_servers": bootstrap,
            "deleted": True,
            "success": True,
        }

    stderr = result.stderr.strip()
    if "UnknownTopicOrPartitionException" in stderr:
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "deleted": False,
            "message": "トピックはブローカー上に存在しません",
            "success": True,
        }

    log.error("delete_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=stderr)
    return {"error": f"トピック削除エラー ({bootstrap}): {stderr or result.stdout.strip()}", "success": False}
