from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from app.core import Settings
from app.platforms.kubernetes import KubernetesOperationError
from app.platforms.kubernetes.services.deployment_manager_service import (
    DeploymentManagerService,
)


@pytest.fixture
def mock_k8s_resources():
    apps_v1_api = MagicMock()
    core_v1_api = MagicMock()
    api_client = MagicMock()
    api_client.sanitize_for_serialization.side_effect = lambda x: x
    clients = MagicMock()
    clients.get_apps_v1_api.return_value = apps_v1_api
    clients.get_core_v1_api.return_value = core_v1_api
    clients.get_api_client.return_value = api_client
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        kubernetes_allowed_namespaces=["default", "chatops-demo", "demo-app"],
    )
    service = DeploymentManagerService(settings, clients)
    return service, apps_v1_api, core_v1_api, api_client


def test_scale_deployment_success(mock_k8s_resources) -> None:
    service, apps_v1_api, core_v1_api, api_client = mock_k8s_resources
    apps_v1_api.patch_namespaced_deployment_scale.return_value = {"status": "scaled"}

    result = service.scale_deployment("my-dep", "demo-app", 3)

    assert result == {"status": "scaled"}
    apps_v1_api.patch_namespaced_deployment_scale.assert_called_once_with(
        name="my-dep", namespace="demo-app", body={"spec": {"replicas": 3}}
    )


def test_scale_deployment_rejected_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _2 = mock_k8s_resources

    with pytest.raises(PermissionError, match="kube-system"):
        service.scale_deployment("my-dep", "kube-system", 3)

    apps_v1_api.patch_namespaced_deployment_scale.assert_not_called()


def test_restart_deployment_success(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _2 = mock_k8s_resources
    apps_v1_api.patch_namespaced_deployment.return_value = {"status": "restarting"}

    result = service.restart_deployment("my-dep", "demo-app")

    assert result == {"status": "restarting"}
    apps_v1_api.patch_namespaced_deployment.assert_called_once()
    call_args = apps_v1_api.patch_namespaced_deployment.call_args[1]
    assert call_args["name"] == "my-dep"
    assert call_args["namespace"] == "demo-app"
    assert (
        "kubectl.kubernetes.io/restartedAt"
        in call_args["body"]["spec"]["template"]["metadata"]["annotations"]
    )


def test_update_deployment_image_success(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _2 = mock_k8s_resources
    apps_v1_api.patch_namespaced_deployment.return_value = {"status": "updating"}

    result = service.update_deployment_image(
        "my-dep", "demo-app", "web", "nginx:latest"
    )

    assert result == {"status": "updating"}
    apps_v1_api.patch_namespaced_deployment.assert_called_once_with(
        name="my-dep",
        namespace="demo-app",
        body={
            "spec": {
                "template": {
                    "spec": {"containers": [{"name": "web", "image": "nginx:latest"}]}
                }
            }
        },
    )


def test_rollback_deployment_no_revisions_error(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _2 = mock_k8s_resources
    apps_v1_api.list_namespaced_replica_set.return_value = SimpleNamespace(items=[])

    with pytest.raises(KubernetesOperationError, match="No revisions were found"):
        service.rollback_deployment("my-dep", "demo-app")


def test_rollback_deployment_only_one_revision_error(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _2 = mock_k8s_resources
    rs = SimpleNamespace(
        metadata=SimpleNamespace(
            owner_references=[SimpleNamespace(kind="Deployment", name="my-dep")],
            annotations={"deployment.kubernetes.io/revision": "1"},
        ),
        spec=SimpleNamespace(template=SimpleNamespace(spec="pod-spec-1")),
    )
    apps_v1_api.list_namespaced_replica_set.return_value = SimpleNamespace(items=[rs])

    with pytest.raises(KubernetesOperationError, match="No previous revision"):
        service.rollback_deployment("my-dep", "demo-app")


def test_rollback_deployment_to_previous_success(mock_k8s_resources) -> None:
    service, apps_v1_api, _, api_client = mock_k8s_resources
    rs1 = SimpleNamespace(
        metadata=SimpleNamespace(
            owner_references=[SimpleNamespace(kind="Deployment", name="my-dep")],
            annotations={"deployment.kubernetes.io/revision": "1"},
        ),
        spec=SimpleNamespace(template=SimpleNamespace(spec="pod-spec-1")),
    )
    rs2 = SimpleNamespace(
        metadata=SimpleNamespace(
            owner_references=[SimpleNamespace(kind="Deployment", name="my-dep")],
            annotations={"deployment.kubernetes.io/revision": "2"},
        ),
        spec=SimpleNamespace(template=SimpleNamespace(spec="pod-spec-2")),
    )
    apps_v1_api.list_namespaced_replica_set.return_value = SimpleNamespace(
        items=[rs1, rs2]
    )
    apps_v1_api.patch_namespaced_deployment.return_value = {"status": "rolled back"}

    result = service.rollback_deployment("my-dep", "demo-app")

    assert result == {"status": "rolled back"}
    apps_v1_api.patch_namespaced_deployment.assert_called_once_with(
        name="my-dep",
        namespace="demo-app",
        body={"spec": {"template": SimpleNamespace(spec="pod-spec-1")}},
    )


def test_rollback_deployment_to_specific_revision_success(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _2 = mock_k8s_resources
    rs1 = SimpleNamespace(
        metadata=SimpleNamespace(
            owner_references=[SimpleNamespace(kind="Deployment", name="my-dep")],
            annotations={"deployment.kubernetes.io/revision": "1"},
        ),
        spec=SimpleNamespace(template=SimpleNamespace(spec="pod-spec-1")),
    )
    rs2 = SimpleNamespace(
        metadata=SimpleNamespace(
            owner_references=[SimpleNamespace(kind="Deployment", name="my-dep")],
            annotations={"deployment.kubernetes.io/revision": "2"},
        ),
        spec=SimpleNamespace(template=SimpleNamespace(spec="pod-spec-2")),
    )
    apps_v1_api.list_namespaced_replica_set.return_value = SimpleNamespace(
        items=[rs1, rs2]
    )
    apps_v1_api.patch_namespaced_deployment.return_value = {
        "status": "rolled back to 1"
    }

    result = service.rollback_deployment("my-dep", "demo-app", revision=1)

    assert result == {"status": "rolled back to 1"}
    apps_v1_api.patch_namespaced_deployment.assert_called_once_with(
        name="my-dep",
        namespace="demo-app",
        body={"spec": {"template": SimpleNamespace(spec="pod-spec-1")}},
    )


def test_rollback_deployment_specific_revision_not_found(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _2 = mock_k8s_resources
    rs1 = SimpleNamespace(
        metadata=SimpleNamespace(
            owner_references=[SimpleNamespace(kind="Deployment", name="my-dep")],
            annotations={"deployment.kubernetes.io/revision": "1"},
        ),
        spec=SimpleNamespace(template=SimpleNamespace(spec="pod-spec-1")),
    )
    apps_v1_api.list_namespaced_replica_set.return_value = SimpleNamespace(items=[rs1])

    with pytest.raises(KubernetesOperationError, match="Revision 3 was not found"):
        service.rollback_deployment("my-dep", "demo-app", revision=3)
