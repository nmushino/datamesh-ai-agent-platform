"""OpenShift Tool 統合テスト。

前提: oc / kubectl コマンドが利用可能で、テスト用 Namespace が存在すること。
CI では SKIP_OPENSHIFT_TESTS=true を設定してスキップ可能。
"""
import os
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def skip_without_oc():
    if os.getenv("SKIP_OPENSHIFT_TESTS", "false").lower() == "true":
        pytest.skip("SKIP_OPENSHIFT_TESTS=true")


class TestGetPods:
    def test_get_pods_default_namespace(self):
        """デフォルト Namespace の Pod 一覧が取得できる。"""
        from tools.openshift.openshift_tools import get_pods

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (True, "NAME\tai-agent-xyz\nREADY\t1/1\nSTATUS\tRunning")
            result = get_pods.invoke({"namespace": "ai-agent-platform"})

        assert result["success"] is True
        assert "pods" in result

    def test_get_pods_command_failure(self):
        """oc コマンドが失敗した場合 success=False を返す。"""
        from tools.openshift.openshift_tools import get_pods

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (False, "Error: namespace not found")
            result = get_pods.invoke({"namespace": "nonexistent-ns"})

        assert result["success"] is False
        assert "error" in result


class TestGetPodLogs:
    def test_get_pod_logs_success(self):
        from tools.openshift.openshift_tools import get_pod_logs

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (True, "2026-06-26 INFO Application started")
            result = get_pod_logs.invoke({
                "pod_name": "ai-agent-orchestrator-abc",
                "namespace": "ai-agent-platform",
                "tail_lines": 50,
            })

        assert result["success"] is True
        assert "logs" in result

    def test_get_pod_logs_pod_not_found(self):
        from tools.openshift.openshift_tools import get_pod_logs

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (False, "Error from server (NotFound): pods 'nonexistent' not found")
            result = get_pod_logs.invoke({
                "pod_name": "nonexistent",
                "namespace": "ai-agent-platform",
            })

        assert result["success"] is False


class TestScaleDeployment:
    def test_scale_deployment_success(self):
        from tools.openshift.openshift_tools import scale_deployment

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (True, "deployment.apps/ai-agent-orchestrator scaled")
            result = scale_deployment.invoke({
                "deployment_name": "ai-agent-orchestrator",
                "replicas": 3,
                "namespace": "ai-agent-platform",
            })

        assert result["success"] is True
        assert result["replicas"] == 3

    def test_scale_deployment_invalid_replicas(self):
        from tools.openshift.openshift_tools import scale_deployment

        result = scale_deployment.invoke({
            "deployment_name": "any",
            "replicas": 99,
        })
        assert result["success"] is False
        assert "error" in result


class TestRestartDeployment:
    def test_restart_deployment_success(self):
        from tools.openshift.openshift_tools import restart_deployment

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (True, "deployment.apps/ai-agent-orchestrator restarted")
            result = restart_deployment.invoke({
                "deployment_name": "ai-agent-orchestrator",
                "namespace": "ai-agent-platform",
            })

        assert result["success"] is True
        assert "再起動" in result["message"]
