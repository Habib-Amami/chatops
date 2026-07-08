from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core import Settings
from app.platforms.kubernetes.services import PodService


def test_pod_service_lists_sanitized_pod_health() -> None:
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="api-123", namespace="chatops-demo"),
        spec=SimpleNamespace(
            node_name="minikube",
            containers=[
                SimpleNamespace(image="example/api:1.0"),
                SimpleNamespace(image="example/sidecar:1.0"),
            ],
        ),
        status=SimpleNamespace(
            phase="Running",
            pod_ip="10.244.0.10",
            container_statuses=[
                SimpleNamespace(ready=True, restart_count=1),
                SimpleNamespace(ready=True, restart_count=0),
            ],
        ),
    )
    core_api = MagicMock()
    core_api.list_namespaced_pod.return_value = SimpleNamespace(items=[pod])
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.list_pods("chatops-demo")

    assert len(result) == 1
    assert result[0].model_dump() == {
        "name": "api-123",
        "namespace": "chatops-demo",
        "phase": "Running",
        "ready": True,
        "restart_count": 1,
        "node_name": "minikube",
        "pod_ip": "10.244.0.10",
        "images": ["example/api:1.0", "example/sidecar:1.0"],
    }
    core_api.list_namespaced_pod.assert_called_once_with(namespace="chatops-demo")


def test_pod_service_rejects_disallowed_namespace() -> None:
    core_api = MagicMock()
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    with pytest.raises(PermissionError, match="kube-system"):
        service.list_pods("kube-system")

    core_api.list_namespaced_pod.assert_not_called()
