from datetime import UTC, datetime
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

    result = service.get_pods("chatops-demo")

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
        service.get_pods("kube-system")

    core_api.list_namespaced_pod.assert_not_called()


def test_pod_service_gets_pod_details() -> None:
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="api-123",
            namespace="chatops-demo",
            labels={"app": "api"},
            creation_timestamp=created_at,
        ),
        spec=SimpleNamespace(
            node_name="minikube",
            containers=[SimpleNamespace(image="example/api:1.0")],
        ),
        status=SimpleNamespace(
            phase="Running",
            pod_ip="10.244.0.10",
            container_statuses=[
                SimpleNamespace(
                    name="api",
                    image="example/api:1.0",
                    ready=True,
                    restart_count=2,
                )
            ],
            conditions=[
                SimpleNamespace(
                    type="Ready",
                    status="True",
                    reason=None,
                    message=None,
                )
            ],
        ),
    )
    core_api = MagicMock()
    core_api.read_namespaced_pod.return_value = pod
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.get_pod("chatops-demo", "api-123")

    assert result.model_dump() == {
        "name": "api-123",
        "namespace": "chatops-demo",
        "phase": "Running",
        "ready": True,
        "restart_count": 2,
        "node_name": "minikube",
        "pod_ip": "10.244.0.10",
        "images": ["example/api:1.0"],
        "labels": {"app": "api"},
        "created_at": "2026-01-02T03:04:05+00:00",
        "containers": [
            {
                "name": "api",
                "image": "example/api:1.0",
                "ready": True,
                "restart_count": 2,
            }
        ],
        "conditions": [
            {
                "type": "Ready",
                "status": "True",
                "reason": None,
                "message": None,
            }
        ],
    }
    core_api.read_namespaced_pod.assert_called_once_with(
        name="api-123",
        namespace="chatops-demo",
    )


def test_pod_service_gets_limited_pod_logs() -> None:
    core_api = MagicMock()
    core_api.read_namespaced_pod_log.return_value = "error log"
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.get_pod_logs(
        "chatops-demo",
        "api-123",
        container="api",
        tail_lines=9999,
    )

    assert result == "error log"
    core_api.read_namespaced_pod_log.assert_called_once_with(
        name="api-123",
        namespace="chatops-demo",
        container="api",
        tail_lines=500,
        timestamps=True,
    )


def test_pod_service_lists_pod_events() -> None:
    first_seen = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    last_seen = datetime(2026, 1, 2, 3, 5, 5, tzinfo=UTC)
    event = SimpleNamespace(
        type="Warning",
        reason="BackOff",
        message="Back-off restarting failed container",
        count=3,
        first_timestamp=first_seen,
        last_timestamp=last_seen,
    )
    core_api = MagicMock()
    core_api.list_namespaced_event.return_value = SimpleNamespace(items=[event])
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.get_pod_events("chatops-demo", "api-123")

    assert [event.model_dump() for event in result] == [
        {
            "type": "Warning",
            "reason": "BackOff",
            "message": "Back-off restarting failed container",
            "count": 3,
            "first_timestamp": "2026-01-02T03:04:05+00:00",
            "last_timestamp": "2026-01-02T03:05:05+00:00",
        }
    ]
    core_api.list_namespaced_event.assert_called_once_with(
        namespace="chatops-demo",
        field_selector="involvedObject.name=api-123,involvedObject.kind=Pod",
    )
