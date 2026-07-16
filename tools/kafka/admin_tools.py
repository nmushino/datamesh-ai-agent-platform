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


# Skupper経由の外部リスナー(9094)は AWS ELB のIP変動やブローカー再起動直後の
# 状態不安定などで断続的にタイムアウトすることを実際に何度も確認した。この
# フォールバックは *-mm2-pause-token の認証情報(mm2-pause-agentサービス
# アカウント、対象ブローカーPodへの pods/exec のみに絞ったRBAC)を再利用して、
# 各サイトクラスタのブローカーPodへ直接 exec し、内部リスナー(localhost:9092、
# Skupperを経由しないため上記の問題の影響を受けない)経由でコマンドを実行する。
# 現時点でこの認証情報が設定されているのは A/B サイトのみ(Cサイトは
# RBAC未適用)。
_BROKER_POD_NAMES = [
    "shop-cluster-shop-cluster-brokers-0",
    "shop-cluster-shop-cluster-brokers-1",
    "shop-cluster-shop-cluster-brokers-2",
]


def _exec_on_broker_pod(site: str, command: list[str]) -> dict:
    """指定サイトのブローカーPod(先頭から順に生きているものを1つ)に対して
    pods/exec でコマンドを実行する。Skupper経由の外部リスナーが不安定な場合の
    フォールバック用。認証情報が無い場合は {"success": False, "unavailable": True}
    を返す(呼び出し元で「フォールバック自体が使えない」と区別できるようにする)。"""
    config = _mm2_api_config(site)
    if config is None:
        return {"success": False, "unavailable": True, "error": "exec認証情報が未設定"}

    api_server, token = config
    try:
        from kubernetes import client as k8s_client
        from kubernetes.stream import stream as k8s_stream
    except ImportError as e:
        return {"success": False, "unavailable": True, "error": f"kubernetesクライアント未導入: {e}"}

    configuration = k8s_client.Configuration()
    configuration.host = api_server
    configuration.api_key = {"authorization": f"Bearer {token}"}
    configuration.verify_ssl = False
    api_client = k8s_client.ApiClient(configuration)
    core_v1 = k8s_client.CoreV1Api(api_client)

    last_error = "対象ブローカーPodが見つかりません"
    for pod_name in _BROKER_POD_NAMES:
        try:
            output = k8s_stream(
                core_v1.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=_MM2_NAMESPACE,
                command=command,
                stderr=True, stdin=False, stdout=True, tty=False,
                _preload_content=True,
                _request_timeout=_CMD_TIMEOUT_SECONDS,
            )
            return {"success": True, "output": output, "pod": pod_name}
        except Exception as e:
            last_error = str(e)
            continue
    return {"success": False, "error": last_error}


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


def _pause_all_mm2() -> list[dict]:
    return [_set_mm2_pause(site, True) for site in _MM2_SITES]


def _resume_all_mm2() -> list[dict]:
    return [_set_mm2_pause(site, False) for site in _MM2_SITES]


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


_SITE_DISPLAY_NAMES = {"asite": "Aサイト", "bsite": "Bサイト", "csite": "Cサイト"}


def _delete_topic_via_cli(bootstrap: str, topic_name: str, timeout_seconds: int) -> dict:
    """Skupper経由の外部リスナー(9094)に対して kafka-topics.sh --delete を実行する。
    exec認証情報が無いサイト(現時点ではCサイト)向けのフォールバックとしてのみ使う。"""
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
    if "UnknownTopicOrPartitionException" in stderr:
        return {"deleted": False, "message": "トピックはブローカー上に存在しません", "success": True}

    return {"error": f"トピック削除エラー ({bootstrap}): {stderr or result.stdout.strip()}", "success": False}


def _delete_topic_on_broker(
    bootstrap: str, topic_name: str, timeout_seconds: int = _CMD_TIMEOUT_SECONDS, site: str | None = None,
) -> dict:
    """指定ブローカー上の指定トピックを削除する内部ヘルパー。
    topic_name/service_name を含まない結果 dict (deleted/success/message/error) を返す。

    Skupper経由の外部リスナー(9094)は AWS ELB のIP変動やブローカー再起動直後の
    状態不安定などで断続的にタイムアウトすることを実際に何度も確認したため、
    site が指定されている場合は常にブローカーPodへの直接exec (内部リスナー
    localhost:9092、Skupperを経由しないため上記の問題の影響を受けない) を
    優先する。exec認証情報が設定されていないサイト(現時点ではCサイト)でのみ、
    従来のSkupper経由CLI呼び出しにフォールバックする。"""
    display_name = _SITE_DISPLAY_NAMES.get(site, site or "")
    if site:
        push_status(f"{display_name}処理中...")
        exec_result = _exec_on_broker_pod(
            site,
            [_KAFKA_TOPICS_CMD, "--delete", "--bootstrap-server", "localhost:9092", "--topic", topic_name],
        )
        if exec_result.get("success"):
            output = exec_result.get("output", "")
            if "UnknownTopicOrPartitionException" in output:
                return {"deleted": False, "message": "トピックはブローカー上に存在しません", "success": True}
            if "Error" in output:
                return {"error": f"トピック削除エラー (exec/{site}): {output}", "success": False}
            return {"deleted": True, "success": True, "via": "exec"}
        if not exec_result.get("unavailable"):
            return {"error": f"トピック削除エラー (exec/{site}): {exec_result.get('error')}", "success": False}
        # exec認証情報が無いサイト(現時点ではCサイト)のみ、ここから下のSkupper
        # 経由CLIフォールバックに進む。
        log.warning("delete_topic_exec_unavailable_falling_back_to_cli", site=site, topic_name=topic_name)

    return _delete_topic_via_cli(bootstrap, topic_name, timeout_seconds)


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
        "topic_name": topic_name,
        "service_name": service_name,
        "bootstrap_servers": bootstrap,
        "deleted": primary["deleted"],
        "success": True,
        "mirror_deletions": mirror_deletions,
    }
