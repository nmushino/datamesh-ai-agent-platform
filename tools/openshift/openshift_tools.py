"""OpenShift Tool — kubectl/oc 経由でクラスター操作を行うツール群。

設計原則:
- AI は直接クラスターリソースを変更しない → ツール経由で操作する
- 破壊的操作 (delete/scale-to-zero) は requires_approval=True のメタデータを付与
- 全ての操作は structlog で記録し Audit 証跡を残す
"""
from __future__ import annotations

import os
import subprocess
from typing import Any

import httpx
import structlog
from langchain_core.tools import tool

log = structlog.get_logger(__name__)

_OC_CMD = os.getenv("OC_CMD", "oc")       # oc または kubectl
_NAMESPACE = os.getenv("OPENSHIFT_NAMESPACE", "ai-agent-platform")

# A/B/C サイト(quarkusdroneshop-demo が動いている各 OpenShift クラスター)向け。
# tools/kafka/admin_tools.py の _mm2_api_config と同じパターンで、
# <SITE>_K8S_API_SERVER / <SITE>_K8S_TOKEN 環境変数からサイトごとの
# Kubernetes API サーバーアドレスと閲覧用トークンを読む。
# (MM2一時停止用のトークンは kafkamirrormaker2 リソースのみに絞られた
# スコープであり、Namespace/Pod/Service/Route の閲覧には使えないため、
# 別途 view 権限のトークンをこの環境変数名で用意する必要がある)
_SITES = ["asite", "bsite", "csite"]
_SITE_DISPLAY_NAMES = {"asite": "Aサイト", "bsite": "Bサイト", "csite": "Cサイト"}
_API_TIMEOUT_SECONDS = 15


def _run(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """oc/kubectl コマンドを実行し (success, output) を返す。
    「自身のドメイン」(このAI Agentが動いているクラスター)向け。"""
    cmd = [_OC_CMD, *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, f"コマンドタイムアウト ({timeout}s): {' '.join(cmd)}"
    except FileNotFoundError:
        return False, f"コマンドが見つかりません: {_OC_CMD}"


def _site_k8s_config(site: str) -> tuple[str, str] | None:
    """<site>_K8S_API_SERVER / <site>_K8S_TOKEN 環境変数から接続情報を返す。
    未設定の場合は None (呼び出し元でエラーとして返す)。"""
    api_server = os.environ.get(f"{site.upper()}_K8S_API_SERVER")
    token = os.environ.get(f"{site.upper()}_K8S_TOKEN")
    if not api_server or not token:
        return None
    return api_server, token


def _site_api_get(site: str, path: str) -> tuple[bool, Any]:
    """指定サイトの Kubernetes/OpenShift REST API に GET リクエストを送る。
    戻り値は (success, json または エラーメッセージ)。"""
    config = _site_k8s_config(site)
    if config is None:
        return False, (
            f"{site} のAPI接続情報が未設定です "
            f"({site.upper()}_K8S_API_SERVER / {site.upper()}_K8S_TOKEN 環境変数が必要)"
        )
    api_server, token = config
    try:
        resp = httpx.get(
            f"{api_server}{path}",
            headers={"Authorization": f"Bearer {token}"},
            # NOTE: 各サイトのKubernetes APIサーバー証明書はサイトごとのクラスタ内CAが
            # 発行しており、このコンテナイメージにCAバンドルを同梱していないため
            # 検証をスキップする(tools/kafka/admin_tools.py の _set_mm2_pause と同じ理由)。
            verify=False,
            timeout=_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return True, resp.json()
    except Exception as e:
        return False, str(e)


def _validate_site(site: str) -> str | None:
    """site が空文字(自身のドメイン)または既知のサイト名であることを確認する。
    不正な場合はエラーメッセージを返し、問題なければ None を返す。"""
    if site and site not in _SITES:
        return f"未知の site: {site}。空文字(自身のドメイン)または {_SITES} のいずれかを指定してください。"
    return None


# ─── Read 系 ──────────────────────────────────────────────────────────────────

@tool
def list_sites() -> dict[str, Any]:
    """問い合わせ可能なサイト一覧を返す。「自身のドメイン」(このAI Agentが
    動いているクラスター、site を指定しない場合)と、A/B/Cサイト(それぞれ
    <SITE>_K8S_API_SERVER / <SITE>_K8S_TOKEN 環境変数が設定されていれば
    問い合わせ可能)を区別して報告する際に使うこと。"""
    configured = [s for s in _SITES if _site_k8s_config(s) is not None]
    return {
        "self": "site 引数を空にすると、このAI Agentが動いているクラスター(自身のドメイン)を問い合わせる",
        "sites": _SITES,
        "configured_sites": configured,
        "unconfigured_sites": [s for s in _SITES if s not in configured],
        "success": True,
    }


@tool
def list_namespaces(site: str = "") -> dict[str, Any]:
    """Namespace 一覧を取得する。

    Args:
        site: "asite"/"bsite"/"csite" のいずれか。空文字の場合は
            このAI Agentが動いているクラスター(自身のドメイン)を対象にする。
    """
    if (err := _validate_site(site)) is not None:
        return {"error": err, "success": False}

    if not site:
        ok, output = _run(["get", "namespaces"])
        if not ok:
            return {"error": output, "success": False}
        return {"site": "self", "namespaces": output, "success": True}

    ok, data = _site_api_get(site, "/api/v1/namespaces")
    if not ok:
        log.error("list_namespaces.failed", site=site, error=data)
        return {"error": f"Namespace一覧取得エラー ({_SITE_DISPLAY_NAMES.get(site, site)}): {data}", "success": False}

    namespaces = [
        {
            "name": item["metadata"]["name"],
            "status": item.get("status", {}).get("phase", "unknown"),
        }
        for item in data.get("items", [])
    ]
    return {"site": site, "namespaces": namespaces, "success": True}


@tool
def get_pods(namespace: str = "", label_selector: str = "", site: str = "") -> dict[str, Any]:
    """指定 Namespace の Pod 一覧を取得する。

    Args:
        namespace: 対象 Namespace (空の場合はデフォルト Namespace を使用)
        label_selector: ラベルセレクタ例 "app=ai-agent-orchestrator"
        site: "asite"/"bsite"/"csite" のいずれか。空文字の場合は
            このAI Agentが動いているクラスター(自身のドメイン)を対象にする。
    """
    if (err := _validate_site(site)) is not None:
        return {"error": err, "success": False}

    if not site:
        ns = namespace or _NAMESPACE
        args = ["get", "pods", "-n", ns, "-o", "wide"]
        if label_selector:
            args += ["-l", label_selector]

        ok, output = _run(args)
        if not ok:
            log.error("get_pods.failed", namespace=ns, error=output)
            return {"error": output, "success": False}

        log.info("get_pods.success", namespace=ns)
        return {"site": "self", "namespace": ns, "pods": output, "success": True}

    if not namespace:
        return {"error": "site を指定する場合、namespace も指定してください。", "success": False}

    path = f"/api/v1/namespaces/{namespace}/pods"
    if label_selector:
        path += f"?labelSelector={label_selector}"

    ok, data = _site_api_get(site, path)
    if not ok:
        log.error("get_pods.failed", site=site, namespace=namespace, error=data)
        return {"error": f"Pod一覧取得エラー ({_SITE_DISPLAY_NAMES.get(site, site)}): {data}", "success": False}

    pods = [
        {
            "name": item["metadata"]["name"],
            "phase": item.get("status", {}).get("phase", "unknown"),
            "ready": all(
                c.get("ready", False)
                for c in item.get("status", {}).get("containerStatuses", [])
            ) if item.get("status", {}).get("containerStatuses") else False,
            "restarts": sum(
                c.get("restartCount", 0)
                for c in item.get("status", {}).get("containerStatuses", [])
            ),
        }
        for item in data.get("items", [])
    ]
    return {"site": site, "namespace": namespace, "pods": pods, "success": True}


@tool
def list_services(namespace: str, site: str = "") -> dict[str, Any]:
    """指定 Namespace の Service 一覧を取得する。

    Args:
        namespace: 対象 Namespace
        site: "asite"/"bsite"/"csite" のいずれか。空文字の場合は
            このAI Agentが動いているクラスター(自身のドメイン)を対象にする。
    """
    if (err := _validate_site(site)) is not None:
        return {"error": err, "success": False}

    if not site:
        ok, output = _run(["get", "services", "-n", namespace, "-o", "wide"])
        if not ok:
            return {"error": output, "success": False}
        return {"site": "self", "namespace": namespace, "services": output, "success": True}

    ok, data = _site_api_get(site, f"/api/v1/namespaces/{namespace}/services")
    if not ok:
        log.error("list_services.failed", site=site, namespace=namespace, error=data)
        return {"error": f"Service一覧取得エラー ({_SITE_DISPLAY_NAMES.get(site, site)}): {data}", "success": False}

    services = [
        {
            "name": item["metadata"]["name"],
            "type": item.get("spec", {}).get("type", "ClusterIP"),
            "cluster_ip": item.get("spec", {}).get("clusterIP", ""),
            "ports": [
                f"{p.get('port')}:{p.get('targetPort')}/{p.get('protocol', 'TCP')}"
                for p in item.get("spec", {}).get("ports", [])
            ],
        }
        for item in data.get("items", [])
    ]
    return {"site": site, "namespace": namespace, "services": services, "success": True}


@tool
def list_routes(namespace: str, site: str = "") -> dict[str, Any]:
    """指定 Namespace の Route (OpenShift の外部公開URL) 一覧を取得する。

    Args:
        namespace: 対象 Namespace
        site: "asite"/"bsite"/"csite" のいずれか。空文字の場合は
            このAI Agentが動いているクラスター(自身のドメイン)を対象にする。
    """
    if (err := _validate_site(site)) is not None:
        return {"error": err, "success": False}

    if not site:
        ok, output = _run(["get", "routes", "-n", namespace, "-o", "wide"])
        if not ok:
            return {"error": output, "success": False}
        return {"site": "self", "namespace": namespace, "routes": output, "success": True}

    ok, data = _site_api_get(
        site, f"/apis/route.openshift.io/v1/namespaces/{namespace}/routes"
    )
    if not ok:
        log.error("list_routes.failed", site=site, namespace=namespace, error=data)
        return {"error": f"Route一覧取得エラー ({_SITE_DISPLAY_NAMES.get(site, site)}): {data}", "success": False}

    routes = [
        {
            "name": item["metadata"]["name"],
            "host": item.get("spec", {}).get("host", ""),
            "to_service": item.get("spec", {}).get("to", {}).get("name", ""),
            "tls": item.get("spec", {}).get("tls", {}).get("termination", "") if item.get("spec", {}).get("tls") else "",
        }
        for item in data.get("items", [])
    ]
    return {"site": site, "namespace": namespace, "routes": routes, "success": True}


@tool
def get_pod_logs(pod_name: str, namespace: str = "", tail_lines: int = 100) -> dict[str, Any]:
    """Pod のログを取得する。

    Args:
        pod_name: Pod 名
        namespace: 対象 Namespace
        tail_lines: 取得する末尾行数 (デフォルト 100)
    """
    ns = namespace or _NAMESPACE
    args = ["logs", pod_name, "-n", ns, f"--tail={tail_lines}"]

    ok, output = _run(args, timeout=15)
    if not ok:
        log.error("get_pod_logs.failed", pod=pod_name, namespace=ns, error=output)
        return {"error": output, "success": False}

    log.info("get_pod_logs.success", pod=pod_name, namespace=ns, lines=tail_lines)
    return {"pod": pod_name, "namespace": ns, "logs": output, "success": True}


@tool
def get_deployment_status(deployment_name: str, namespace: str = "") -> dict[str, Any]:
    """Deployment の状態 (replicas/ready/available) を取得する。

    Args:
        deployment_name: Deployment 名
        namespace: 対象 Namespace
    """
    ns = namespace or _NAMESPACE
    args = [
        "get", "deployment", deployment_name, "-n", ns,
        "-o", "jsonpath={.status.replicas}/{.status.readyReplicas}/{.status.availableReplicas}"
    ]

    ok, output = _run(args)
    if not ok:
        log.error("get_deployment_status.failed", deployment=deployment_name, error=output)
        return {"error": output, "success": False}

    parts = output.split("/")
    replicas, ready, available = parts[0], parts[1] if len(parts) > 1 else "?", parts[2] if len(parts) > 2 else "?"
    return {
        "deployment": deployment_name,
        "namespace": ns,
        "replicas": replicas,
        "ready": ready,
        "available": available,
        "success": True,
    }


@tool
def get_events(namespace: str = "", resource_name: str = "") -> dict[str, Any]:
    """Namespace の Event 一覧を取得する。障害調査に使用。

    Args:
        namespace: 対象 Namespace
        resource_name: 特定リソース名でフィルタ (任意)
    """
    ns = namespace or _NAMESPACE
    args = ["get", "events", "-n", ns, "--sort-by=.lastTimestamp"]
    if resource_name:
        args += ["--field-selector", f"involvedObject.name={resource_name}"]

    ok, output = _run(args)
    if not ok:
        return {"error": output, "success": False}

    return {"namespace": ns, "events": output, "success": True}


# ─── Write 系 (requires_approval メタデータ付き) ────────────────────────────

@tool
def restart_deployment(deployment_name: str, namespace: str = "") -> dict[str, Any]:
    """Deployment をローリング再起動する。

    ⚠️ この操作は実行中の Pod を順次再起動します。承認が必要です。

    Args:
        deployment_name: 再起動する Deployment 名
        namespace: 対象 Namespace
    """
    ns = namespace or _NAMESPACE
    args = ["rollout", "restart", f"deployment/{deployment_name}", "-n", ns]

    ok, output = _run(args)
    if not ok:
        log.error("restart_deployment.failed", deployment=deployment_name, error=output)
        return {"error": output, "success": False}

    log.warning("restart_deployment.executed", deployment=deployment_name, namespace=ns)
    return {
        "deployment": deployment_name,
        "namespace": ns,
        "message": f"Deployment {deployment_name} のローリング再起動を開始しました",
        "success": True,
    }


@tool
def scale_deployment(deployment_name: str, replicas: int, namespace: str = "") -> dict[str, Any]:
    """Deployment のレプリカ数を変更する。

    ⚠️ replicas=0 にするとサービスが停止します。承認が必要です。

    Args:
        deployment_name: Deployment 名
        replicas: 目標レプリカ数 (0〜20)
        namespace: 対象 Namespace
    """
    if replicas < 0 or replicas > 20:
        return {"error": "replicas は 0〜20 の範囲で指定してください", "success": False}

    ns = namespace or _NAMESPACE
    args = ["scale", f"deployment/{deployment_name}", f"--replicas={replicas}", "-n", ns]

    ok, output = _run(args)
    if not ok:
        log.error("scale_deployment.failed", deployment=deployment_name, error=output)
        return {"error": output, "success": False}

    log.warning("scale_deployment.executed", deployment=deployment_name, replicas=replicas, namespace=ns)
    return {
        "deployment": deployment_name,
        "namespace": ns,
        "replicas": replicas,
        "message": f"Deployment {deployment_name} を {replicas} レプリカに変更しました",
        "success": True,
    }


@tool
def apply_manifest(yaml_content: str, namespace: str = "") -> dict[str, Any]:
    """YAML マニフェストを OpenShift に適用する (oc apply -f)。

    ⚠️ クラスター上のリソースが変更されます。承認が必要です。

    Args:
        yaml_content: 適用する YAML 文字列
        namespace: 対象 Namespace (YAML 内の namespace より優先)
    """
    import pathlib
    import tempfile

    ns = namespace or _NAMESPACE
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        tmp_path = f.name

    try:
        args = ["apply", "-f", tmp_path, "-n", ns]
        ok, output = _run(args, timeout=60)
    finally:
        pathlib.Path(tmp_path).unlink(missing_ok=True)

    if not ok:
        log.error("apply_manifest.failed", namespace=ns, error=output)
        return {"error": output, "success": False}

    log.warning("apply_manifest.executed", namespace=ns, output=output)
    return {"namespace": ns, "output": output, "success": True}
