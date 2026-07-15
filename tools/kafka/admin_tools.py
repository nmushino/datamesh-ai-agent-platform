"""サイトの Kafka ブローカーに対する実トピック作成ツール。

OpenMetadata に登録されている A/B/C サイトの messagingService
(external-shop-cluster-kafka-Xsite:9094) は、Skupper 経由で
quarkusdroneshop-rhdh namespace 内にサービスとして公開されている。
OpenMetadata へのメタデータ登録(register_topic_metadata)とは別に、
このツールで実際のブローカー上にトピックを作成する。
"""
from __future__ import annotations

import structlog
# librdkafka バインディングの管理クライアント。kafka-python は Kafka 4.x
# (KRaft) ブローカーの ApiVersions ネゴシエーションと非互換で
# NodeNotReadyError/NoBrokersAvailable になるため、実ブローカーへの
# 管理操作 (トピック作成等) はこちらを使う。
from confluent_kafka import KafkaException as RdKafkaException
from confluent_kafka.admin import AdminClient as RdKafkaAdminClient
from confluent_kafka.admin import NewTopic as RdKafkaNewTopic
from langchain_core.tools import tool

log = structlog.get_logger()

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
        admin = RdKafkaAdminClient({"bootstrap.servers": bootstrap, "client.id": "ai-agent-topic-admin"})
        futures = admin.create_topics(
            [RdKafkaNewTopic(topic_name, num_partitions=partitions, replication_factor=replication_factor)],
            request_timeout=10,
        )
        futures[topic_name].result(timeout=10)
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "bootstrap_servers": bootstrap,
            "created": True,
            "success": True,
        }
    except RdKafkaException as e:
        if e.args and e.args[0].code() == "TOPIC_ALREADY_EXISTS":
            return {
                "topic_name": topic_name,
                "service_name": service_name,
                "created": False,
                "message": "トピックは既にブローカー上に存在します",
                "success": True,
            }
        log.error("create_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=str(e))
        return {"error": f"トピック作成エラー ({bootstrap}): {str(e)}", "success": False}
    except Exception as e:
        log.error("create_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=str(e))
        return {"error": f"トピック作成エラー ({bootstrap}): {str(e)}", "success": False}
