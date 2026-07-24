"""OpenShift Tool 統合テスト。

前提: oc / kubectl コマンドが利用可能で、テスト用 Namespace が存在すること。
CI では SKIP_OPENSHIFT_TESTS=true を設定してスキップ可能。
"""
import os
from unittest.mock import patch

import pytest

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


class TestListSites:
    def test_list_sites_reports_configured_and_unconfigured(self):
        from tools.openshift.openshift_tools import list_sites

        with patch.dict(os.environ, {"ASITE_K8S_API_SERVER": "https://a", "ASITE_K8S_TOKEN": "tok"}, clear=False):
            for key in ("BSITE_K8S_API_SERVER", "BSITE_K8S_TOKEN", "CSITE_K8S_API_SERVER", "CSITE_K8S_TOKEN"):
                os.environ.pop(key, None)
            result = list_sites.invoke({})

        assert result["success"] is True
        assert "asite" in result["configured_sites"]
        assert "bsite" in result["unconfigured_sites"]


class TestListNamespaces:
    def test_list_namespaces_self_uses_oc(self):
        from tools.openshift.openshift_tools import list_namespaces

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (True, "NAME\tai-agent-platform")
            result = list_namespaces.invoke({})

        assert result["success"] is True
        assert result["site"] == "self"

    def test_list_namespaces_site_without_credentials_fails(self):
        from tools.openshift.openshift_tools import list_namespaces

        for key in ("ASITE_K8S_API_SERVER", "ASITE_K8S_TOKEN"):
            os.environ.pop(key, None)
        result = list_namespaces.invoke({"site": "asite"})

        assert result["success"] is False
        assert "ASITE_K8S_API_SERVER" in result["error"]

    def test_list_namespaces_unknown_site_fails(self):
        from tools.openshift.openshift_tools import list_namespaces

        result = list_namespaces.invoke({"site": "dsite"})

        assert result["success"] is False


class TestGetPodsSite:
    def test_get_pods_site_requires_namespace(self):
        from tools.openshift.openshift_tools import get_pods

        with patch.dict(os.environ, {"ASITE_K8S_API_SERVER": "https://a", "ASITE_K8S_TOKEN": "tok"}, clear=False):
            result = get_pods.invoke({"site": "asite"})

        assert result["success"] is False
        assert "namespace" in result["error"]

    def test_get_pods_site_success(self):
        from tools.openshift.openshift_tools import get_pods

        fake_response = {
            "items": [
                {
                    "metadata": {"name": "qdca10-abc"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"ready": True, "restartCount": 0}],
                    },
                }
            ]
        }
        with (
            patch.dict(os.environ, {"ASITE_K8S_API_SERVER": "https://a", "ASITE_K8S_TOKEN": "tok"}, clear=False),
            patch("tools.openshift.openshift_tools._site_api_get") as mock_get,
        ):
            mock_get.return_value = (True, fake_response)
            result = get_pods.invoke({"site": "asite", "namespace": "quarkusdroneshop-demo"})

        assert result["success"] is True
        assert result["pods"][0]["name"] == "qdca10-abc"
        assert result["pods"][0]["ready"] is True


class TestListServicesAndRoutes:
    def test_list_services_self_uses_oc(self):
        from tools.openshift.openshift_tools import list_services

        with patch("tools.openshift.openshift_tools._run") as mock_run:
            mock_run.return_value = (True, "NAME\tweb")
            result = list_services.invoke({"namespace": "quarkusdroneshop-demo"})

        assert result["success"] is True
        assert result["site"] == "self"

    def test_list_routes_site_success(self):
        from tools.openshift.openshift_tools import list_routes

        fake_response = {
            "items": [
                {
                    "metadata": {"name": "web"},
                    "spec": {"host": "web-quarkusdroneshop-demo.apps.example.com", "to": {"name": "web"}},
                }
            ]
        }
        with (
            patch.dict(os.environ, {"BSITE_K8S_API_SERVER": "https://b", "BSITE_K8S_TOKEN": "tok"}, clear=False),
            patch("tools.openshift.openshift_tools._site_api_get") as mock_get,
        ):
            mock_get.return_value = (True, fake_response)
            result = list_routes.invoke({"site": "bsite", "namespace": "quarkusdroneshop-demo"})

        assert result["success"] is True
        assert result["routes"][0]["host"] == "web-quarkusdroneshop-demo.apps.example.com"


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
