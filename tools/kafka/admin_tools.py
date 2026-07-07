"""サイトの Kafka ブローカーに対する実トピック作成ツール。

OpenMetadata に登録されている A/B/C サイトの messagingService
(external-shop-cluster-kafka-Xsite:9094) は、Skupper 経由で
openmetadata namespace 内にサービスとして公開されている。
OpenMetadata へのメタデータ登録(register_topic_metadata)とは別に、
このツールで実際のブローカー上にトピックを作成する。
"""
from __future__ import annotations

import structlog
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from langchain_core.tools import tool

log = structlog.get_logger()

# NOTE: これらのブローカーは ai-agent-orchestrator と別 namespace (openmetadata) で
# Skupper により公開されているサービスのため、Fully Qualified な
# クラスタ内DNS名を使う必要がある(同一namespace名のみでは解決できない)。
_SITE_BOOTSTRAP_SERVERS = {
    "external-shop-cluster-kafka-asite:9094": "external-shop-cluster-kafka-asite.openmetadata.svc.cluster.local:9094",
    "external-shop-cluster-kafka-bsite:9094": "external-shop-cluster-kafka-bsite.openmetadata.svc.cluster.local:9094",
    "external-shop-cluster-kafka-csite:9094": "external-shop-cluster-kafka-csite.openmetadata.svc.cluster.local:9094",
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
    admin = None
    try:
        admin = KafkaAdminClient(bootstrap_servers=bootstrap, client_id="ai-agent-topic-admin", request_timeout_ms=10000)
        admin.create_topics([NewTopic(name=topic_name, num_partitions=partitions, replication_factor=replication_factor)])
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "bootstrap_servers": bootstrap,
            "created": True,
            "success": True,
        }
    except TopicAlreadyExistsError:
        return {
            "topic_name": topic_name,
            "service_name": service_name,
            "created": False,
            "message": "トピックは既にブローカー上に存在します",
            "success": True,
        }
    except Exception as e:
        log.error("create_kafka_topic_failed", topic_name=topic_name, service_name=service_name, error=str(e))
        return {"error": f"トピック作成エラー ({bootstrap}): {str(e)}", "success": False}
    finally:
        if admin:
            admin.close()
