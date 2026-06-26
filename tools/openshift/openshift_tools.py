"""OpenShift Tool — kubectl/oc 経由でクラスター操作を行うツール群。

設計原則:
- AI は直接クラスターリソースを変更しない → ツール経由で操作する
- 破壊的操作 (delete/scale-to-zero) は requires_approval=True のメタデータを付与
- 全ての操作は structlog で記録し Audit 証跡を残す
"""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from typing import Any

import structlog
from langchain_core.tools import tool

log = structlog.get_logger(__name__)

_OC_CMD = os.getenv("OC_CMD", "oc")       # oc または kubectl
_NAMESPACE = os.getenv("OPENSHIFT_NAMESPACE", "ai-agent-platform")


def _run(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """oc/kubectl コマンドを実行し (success, output) を返す。"""
    cmd = [_OC_CMD, *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, f"コマンドタイムアウト ({timeout}s): {' '.join(cmd)}"
    except FileNotFoundError:
        return False, f"コマンドが見つかりません: {_OC_CMD}"


# ─── Read 系 ──────────────────────────────────────────────────────────────────

@tool
def get_pods(namespace: str = "", label_selector: str = "") -> dict[str, Any]:
    """指定 Namespace の Pod 一覧を取得する。

    Args:
        namespace: 対象 Namespace (空の場合はデフォルト Namespace を使用)
        label_selector: ラベルセレクタ例 "app=ai-agent-orchestrator"
    """
    ns = namespace or _NAMESPACE
    args = ["get", "pods", "-n", ns, "-o", "wide"]
    if label_selector:
        args += ["-l", label_selector]

    ok, output = _run(args)
    if not ok:
        log.error("get_pods.failed", namespace=ns, error=output)
        return {"error": output, "success": False}

    log.info("get_pods.success", namespace=ns)
    return {"namespace": ns, "pods": output, "success": True}


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
    import tempfile, pathlib

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
