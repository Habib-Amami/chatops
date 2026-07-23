"""Unit tests for DeploymentManagerService — all 13 methods."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core import Settings
from app.platforms.kubernetes import (
    KubernetesOperationError,
)
from app.platforms.kubernetes.services.deployment_manager_service import (
    DeploymentManagerService,
)


# ──────────────────────────────────────────────────────────────────────────────
# Shared fixture
# ──────────────────────────────────────────────────────────────────────────────


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


# ──────────────────────────────────────────────────────────────────────────────
# ORIGINAL TESTS — scale / restart / update / rollback
# ──────────────────────────────────────────────────────────────────────────────


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


# ──────────────────────────────────────────────────────────────────────────────
# NEW TESTS — list_deployments
# ──────────────────────────────────────────────────────────────────────────────


def test_list_deployments_returns_summary(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    dep = SimpleNamespace(
        metadata=SimpleNamespace(
            name="backend",
            namespace="demo-app",
            labels={"app": "backend"},
        ),
        spec=SimpleNamespace(replicas=2, paused=False),
        status=SimpleNamespace(
            ready_replicas=2,
            available_replicas=2,
            updated_replicas=2,
            conditions=[
                SimpleNamespace(
                    type="Available",
                    status="True",
                    reason="MinimumReplicasAvailable",
                    message="Deployment has minimum availability.",
                )
            ],
        ),
    )
    apps_v1_api.list_namespaced_deployment.return_value = SimpleNamespace(items=[dep])

    result = service.list_deployments("demo-app")

    assert len(result) == 1
    assert result[0]["name"] == "backend"
    assert result[0]["desired_replicas"] == 2
    assert result[0]["ready_replicas"] == 2
    assert result[0]["paused"] is False
    assert result[0]["conditions"][0]["type"] == "Available"


def test_list_deployments_rejected_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources

    with pytest.raises(PermissionError, match="kube-system"):
        service.list_deployments("kube-system")

    apps_v1_api.list_namespaced_deployment.assert_not_called()


def test_list_deployments_empty_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    apps_v1_api.list_namespaced_deployment.return_value = SimpleNamespace(items=[])

    result = service.list_deployments("demo-app")

    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# NEW TESTS — get_deployment
# ──────────────────────────────────────────────────────────────────────────────


def test_get_deployment_returns_details(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    container = SimpleNamespace(name="backend", image="myapp:v1", ports=[])
    dep = SimpleNamespace(
        metadata=SimpleNamespace(
            name="backend",
            namespace="demo-app",
            labels={"app": "backend"},
            annotations={},
            creation_timestamp=None,
        ),
        spec=SimpleNamespace(
            replicas=1,
            paused=None,
            strategy=SimpleNamespace(type="RollingUpdate"),
            template=SimpleNamespace(
                spec=SimpleNamespace(containers=[container])
            ),
        ),
        status=SimpleNamespace(
            ready_replicas=1,
            available_replicas=1,
            updated_replicas=1,
            conditions=[],
        ),
    )
    apps_v1_api.read_namespaced_deployment.return_value = dep

    result = service.get_deployment("backend", "demo-app")

    assert result["name"] == "backend"
    assert result["desired_replicas"] == 1
    assert result["strategy"] == "RollingUpdate"
    assert result["containers"][0]["name"] == "backend"
    assert result["containers"][0]["image"] == "myapp:v1"


def test_get_deployment_rejected_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources

    with pytest.raises(PermissionError, match="kube-system"):
        service.get_deployment("my-dep", "kube-system")

    apps_v1_api.read_namespaced_deployment.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# NEW TESTS — get_deployment_status
# ──────────────────────────────────────────────────────────────────────────────


def test_get_deployment_status_complete(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    dep = SimpleNamespace(
        spec=SimpleNamespace(replicas=3, paused=False),
        status=SimpleNamespace(
            ready_replicas=3,
            available_replicas=3,
            updated_replicas=3,
            conditions=[],
        ),
    )
    apps_v1_api.read_namespaced_deployment_status.return_value = dep

    result = service.get_deployment_status("backend", "demo-app")

    assert result["rollout_state"] == "complete"
    assert result["ready_replicas"] == 3
    assert result["desired_replicas"] == 3


def test_get_deployment_status_degraded(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    dep = SimpleNamespace(
        spec=SimpleNamespace(replicas=3, paused=False),
        status=SimpleNamespace(
            ready_replicas=1,
            available_replicas=1,
            updated_replicas=3,
            conditions=[],
        ),
    )
    apps_v1_api.read_namespaced_deployment_status.return_value = dep

    result = service.get_deployment_status("backend", "demo-app")

    assert result["rollout_state"] == "degraded"


def test_get_deployment_status_in_progress(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    dep = SimpleNamespace(
        spec=SimpleNamespace(replicas=3, paused=False),
        status=SimpleNamespace(
            ready_replicas=3,
            available_replicas=3,
            updated_replicas=1,
            conditions=[],
        ),
    )
    apps_v1_api.read_namespaced_deployment_status.return_value = dep

    result = service.get_deployment_status("backend", "demo-app")

    assert result["rollout_state"] == "in_progress"


def test_get_deployment_status_rejected_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources

    with pytest.raises(PermissionError, match="kube-system"):
        service.get_deployment_status("backend", "kube-system")

    apps_v1_api.read_namespaced_deployment_status.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# NEW TESTS — get_deployment_history
# ──────────────────────────────────────────────────────────────────────────────


def _make_rs(name: str, revision: str, owner: str, image: str) -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            owner_references=[SimpleNamespace(kind="Deployment", name=owner)],
            annotations={
                "deployment.kubernetes.io/revision": revision,
                "kubernetes.io/change-cause": f"deploy {image}",
            },
            creation_timestamp=None,
        ),
        spec=SimpleNamespace(
            template=SimpleNamespace(
                spec=SimpleNamespace(
                    containers=[SimpleNamespace(image=image)]
                )
            )
        ),
    )


def test_get_deployment_history_sorted(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    rs1 = _make_rs("rs-1", "1", "backend", "myapp:v1")
    rs2 = _make_rs("rs-2", "2", "backend", "myapp:v2")
    # rs3 belongs to a different deployment — must be excluded
    rs3 = _make_rs("rs-3", "1", "other-dep", "other:v1")
    apps_v1_api.list_namespaced_replica_set.return_value = SimpleNamespace(
        items=[rs2, rs3, rs1]  # intentionally unsorted
    )

    result = service.get_deployment_history("backend", "demo-app")

    assert result["total_revisions"] == 2
    assert result["revisions"][0]["revision"] == 1
    assert result["revisions"][1]["revision"] == 2
    assert result["revisions"][0]["images"] == ["myapp:v1"]
    assert result["revisions"][1]["images"] == ["myapp:v2"]


def test_get_deployment_history_empty(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    apps_v1_api.list_namespaced_replica_set.return_value = SimpleNamespace(items=[])

    result = service.get_deployment_history("backend", "demo-app")

    assert result["total_revisions"] == 0
    assert result["revisions"] == []


def test_get_deployment_history_rejected_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources

    with pytest.raises(PermissionError, match="kube-system"):
        service.get_deployment_history("backend", "kube-system")

    apps_v1_api.list_namespaced_replica_set.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# NEW TESTS — create_deployment
# ──────────────────────────────────────────────────────────────────────────────


def test_create_deployment_success(mock_k8s_resources) -> None:
    service, apps_v1_api, _, api_client = mock_k8s_resources
    api_client.sanitize_for_serialization.return_value = {"kind": "Deployment"}
    apps_v1_api.create_namespaced_deployment.return_value = {"kind": "Deployment"}

    result = service.create_deployment(
        name="chatops-test",
        namespace="demo-app",
        image="nginx:alpine",
        replicas=2,
        port=80,
    )

    assert result == {"kind": "Deployment"}
    apps_v1_api.create_namespaced_deployment.assert_called_once()
    call_kwargs = apps_v1_api.create_namespaced_deployment.call_args[1]
    assert call_kwargs["namespace"] == "demo-app"
    dep_body = call_kwargs["body"]
    assert dep_body.metadata.name == "chatops-test"
    assert dep_body.spec.replicas == 2
    assert dep_body.spec.template.spec.containers[0].image == "nginx:alpine"


def test_create_deployment_default_replicas(mock_k8s_resources) -> None:
    service, apps_v1_api, _, api_client = mock_k8s_resources
    api_client.sanitize_for_serialization.return_value = {}
    apps_v1_api.create_namespaced_deployment.return_value = {}

    service.create_deployment(name="api", namespace="demo-app", image="myapp:v1")

    call_kwargs = apps_v1_api.create_namespaced_deployment.call_args[1]
    assert call_kwargs["body"].spec.replicas == 1  # default


def test_create_deployment_rejected_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources

    with pytest.raises(PermissionError, match="kube-system"):
        service.create_deployment("dep", "kube-system", "nginx:alpine")

    apps_v1_api.create_namespaced_deployment.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# NEW TESTS — delete_deployment
# ──────────────────────────────────────────────────────────────────────────────


def test_delete_deployment_success(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources
    apps_v1_api.delete_namespaced_deployment.return_value = None

    result = service.delete_deployment("backend", "demo-app")

    assert result["status"] == "deleted"
    assert result["deployment"] == "backend"
    assert result["namespace"] == "demo-app"
    apps_v1_api.delete_namespaced_deployment.assert_called_once()
    call_kwargs = apps_v1_api.delete_namespaced_deployment.call_args[1]
    assert call_kwargs["name"] == "backend"
    assert call_kwargs["namespace"] == "demo-app"


def test_delete_deployment_rejected_namespace(mock_k8s_resources) -> None:
    service, apps_v1_api, _, _api = mock_k8s_resources

    with pytest.raises(PermissionError, match="kube-system"):
        service.delete_deployment("backend", "kube-system")

    apps_v1_api.delete_namespaced_deployment.assert_not_called()
