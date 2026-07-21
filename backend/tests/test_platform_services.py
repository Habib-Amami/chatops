from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError
from urllib3.response import HTTPResponse

from app.core import Settings
from app.platforms.kubernetes import (
    KubernetesAccessDeniedError,
    KubernetesOperationError,
    KubernetesResourceNotFoundError,
)
from app.platforms.kubernetes.services import PodService
from app.platforms.kubernetes.registry import (
    ContainerImageReference,
    ContainerRegistryClient,
)
from app.platforms.kubernetes.verification import PodMutationVerifier
from app.platforms.kubernetes.models import PodCreateResult, PodDeleteResult


def test_pod_service_lists_sanitized_pod_health() -> None:
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="api-123", namespace="chatops-demo"),
        spec=SimpleNamespace(
            node_name="minikube",
            containers=[
                SimpleNamespace(name="api", image="example/api:1.0"),
                SimpleNamespace(name="sidecar", image="example/sidecar:1.0"),
            ],
        ),
        status=SimpleNamespace(
            phase="Running",
            pod_ip="10.244.0.10",
            container_statuses=[
                SimpleNamespace(name="api", ready=True, restart_count=1),
                SimpleNamespace(name="sidecar", ready=True, restart_count=0),
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
            owner_references=[
                SimpleNamespace(
                    kind="ReplicaSet",
                    name="api-7b96f6dcb5",
                    uid="owner-uid",
                    controller=True,
                )
            ],
        ),
        spec=SimpleNamespace(
            node_name="minikube",
            containers=[
                SimpleNamespace(name="api", image="example/api:1.0"),
                SimpleNamespace(
                    name="sidecar",
                    image="example/sidecar:1.0",
                ),
            ],
            init_containers=[
                SimpleNamespace(name="migrate", image="example/migrate:1.0")
            ],
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
            init_container_statuses=[],
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
        "ready": False,
        "restart_count": 2,
        "node_name": "minikube",
        "pod_ip": "10.244.0.10",
        "images": ["example/api:1.0", "example/sidecar:1.0"],
        "labels": {"app": "api"},
        "created_at": "2026-01-02T03:04:05+00:00",
        "containers": [
            {
                "name": "api",
                "image": "example/api:1.0",
                "ready": True,
                "restart_count": 2,
            },
            {
                "name": "sidecar",
                "image": "example/sidecar:1.0",
                "ready": False,
                "restart_count": 0,
            },
        ],
        "init_containers": [
            {
                "name": "migrate",
                "image": "example/migrate:1.0",
                "ready": False,
                "restart_count": 0,
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
        "owners": [
            {
                "kind": "ReplicaSet",
                "name": "api-7b96f6dcb5",
                "uid": "owner-uid",
                "controller": True,
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
        previous=True,
        since_seconds=999_999,
    )

    assert result == "error log"
    core_api.read_namespaced_pod_log.assert_called_once_with(
        name="api-123",
        namespace="chatops-demo",
        container="api",
        tail_lines=200,
        timestamps=True,
        previous=True,
        since_seconds=86_400,
        _preload_content=False,
    )


def test_pod_service_decodes_byte_logs() -> None:
    core_api = MagicMock()
    core_api.read_namespaced_pod_log.return_value = (
        b"2026-01-02 first line\n2026-01-02 second line\n"
    )
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.get_pod_logs("chatops-demo", "api-123")

    assert result == "2026-01-02 first line\n2026-01-02 second line\n"
    assert "b'" not in result


def test_pod_service_decodes_raw_http_log_response() -> None:
    core_api = MagicMock()
    core_api.read_namespaced_pod_log.return_value = HTTPResponse(
        body=b"2026-01-02 first line\n2026-01-02 second line\n",
        preload_content=True,
    )
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.get_pod_logs("chatops-demo", "api-123")

    assert result == "2026-01-02 first line\n2026-01-02 second line\n"
    assert "b'" not in result


def test_pod_service_returns_decoded_logs_without_presentation_formatting() -> None:
    logs = "\n".join(
        f"line-{line_number:03d} " + ("x" * 100) for line_number in range(100)
    )
    core_api = MagicMock()
    core_api.read_namespaced_pod_log.return_value = logs
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.get_pod_logs("chatops-demo", "api-123")

    assert result == logs


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
        limit=20,
    )


def test_pod_service_diagnoses_waiting_container() -> None:
    container_status = SimpleNamespace(
        name="api",
        ready=False,
        restart_count=4,
        state=SimpleNamespace(
            running=None,
            terminated=None,
            waiting=SimpleNamespace(
                reason="ImagePullBackOff",
                message="Back-off pulling image",
            ),
        ),
        last_state=SimpleNamespace(
            running=None,
            waiting=None,
            terminated=SimpleNamespace(
                reason="Error",
                message="Process exited",
                exit_code=1,
                signal=9,
                started_at=None,
                finished_at=None,
            ),
        ),
    )
    init_container_status = SimpleNamespace(
        name="migrate",
        ready=True,
        restart_count=0,
        state=SimpleNamespace(
            running=None,
            waiting=None,
            terminated=SimpleNamespace(
                reason="Completed",
                message=None,
                exit_code=0,
                signal=None,
                started_at=None,
                finished_at=None,
            ),
        ),
        last_state=None,
    )
    pod = SimpleNamespace(
        status=SimpleNamespace(
            phase="Pending",
            container_statuses=[container_status],
            init_container_statuses=[init_container_status],
            ephemeral_container_statuses=[],
            reason=None,
            message=None,
        )
    )
    core_api = MagicMock()
    core_api.read_namespaced_pod_status.return_value = pod
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.diagnose_pod_status("chatops-demo", "api-123")

    assert result.model_dump() == {
        "pod_name": "api-123",
        "namespace": "chatops-demo",
        "phase": "Pending",
        "containers": [
            {
                "state": "Terminated",
                "reason": "Completed",
                "message": None,
                "exit_code": 0,
                "signal": None,
                "started_at": None,
                "finished_at": None,
                "name": "migrate",
                "container_type": "init",
                "ready": True,
                "restart_count": 0,
                "last_state": None,
            },
            {
                "state": "Waiting",
                "reason": "ImagePullBackOff",
                "message": "Back-off pulling image",
                "exit_code": None,
                "signal": None,
                "started_at": None,
                "finished_at": None,
                "name": "api",
                "container_type": "container",
                "ready": False,
                "restart_count": 4,
                "last_state": {
                    "state": "Terminated",
                    "reason": "Error",
                    "message": "Process exited",
                    "exit_code": 1,
                    "signal": 9,
                    "started_at": None,
                    "finished_at": None,
                },
            },
        ],
        "reason": None,
        "message": None,
    }
    core_api.read_namespaced_pod_status.assert_called_once_with(
        name="api-123",
        namespace="chatops-demo",
    )


def test_pod_service_requests_pod_deletion() -> None:
    core_api = MagicMock()
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    mutation_verifier = MagicMock(spec=PodMutationVerifier)
    mutation_verifier.verify_deletion.return_value = PodDeleteResult(
        pod_name="api-123",
        namespace="chatops-demo",
        status="deleted",
        deleted=True,
    )
    service = PodService(
        settings,
        clients,
        mutation_verifier=mutation_verifier,
    )

    result = service.delete_pod("chatops-demo", "api-123")

    assert result.model_dump() == {
        "pod_name": "api-123",
        "namespace": "chatops-demo",
        "status": "deleted",
        "deleted": True,
        "verification_message": None,
    }
    core_api.delete_namespaced_pod.assert_called_once_with(
        name="api-123",
        namespace="chatops-demo",
    )
    mutation_verifier.verify_deletion.assert_called_once_with(
        namespace="chatops-demo",
        pod_name="api-123",
    )


def test_pod_service_verifies_and_creates_standalone_pod() -> None:
    core_api = MagicMock()
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    registry_client = MagicMock(spec=ContainerRegistryClient)
    image_reference = ContainerImageReference(
        registry="docker.io",
        repository="library/nginx",
        tag="alpine",
    )
    registry_client.resolve.return_value = image_reference
    mutation_verifier = MagicMock(spec=PodMutationVerifier)
    mutation_verifier.verify_creation.return_value = PodCreateResult(
        pod_name="manual-test",
        namespace="chatops-demo",
        image="docker.io/library/nginx:alpine",
        registry="docker.io",
        status="ready",
        phase="Running",
        ready=True,
    )
    service = PodService(
        settings,
        clients,
        registry_client,
        mutation_verifier,
    )

    result = service.create_pod(
        "chatops-demo",
        "manual-test",
        "nginx:alpine",
    )

    assert result.model_dump() == {
        "pod_name": "manual-test",
        "namespace": "chatops-demo",
        "image": "docker.io/library/nginx:alpine",
        "registry": "docker.io",
        "manifest_verified": True,
        "status": "ready",
        "phase": "Running",
        "ready": True,
        "verification_message": None,
    }
    registry_client.resolve.assert_called_once_with("nginx:alpine", None)
    registry_client.verify_exists.assert_called_once_with(image_reference)
    mutation_verifier.verify_creation.assert_called_once_with(
        namespace="chatops-demo",
        pod_name="manual-test",
        image="docker.io/library/nginx:alpine",
        registry="docker.io",
    )
    call = core_api.create_namespaced_pod.call_args
    assert call.kwargs["namespace"] == "chatops-demo"
    pod = call.kwargs["body"]
    assert pod.metadata.name == "manual-test"
    assert pod.metadata.owner_references is None
    assert pod.metadata.labels == {
        "app.kubernetes.io/managed-by": "chatops",
        "chatops-purpose": "standalone-test",
    }
    assert pod.spec.automount_service_account_token is False
    assert pod.spec.restart_policy == "Never"
    assert pod.spec.security_context.seccomp_profile.type == "RuntimeDefault"
    assert len(pod.spec.containers) == 1
    container = pod.spec.containers[0]
    assert container.name == "main"
    assert container.image == "docker.io/library/nginx:alpine"
    assert container.resources.requests == {"cpu": "50m", "memory": "64Mi"}
    assert container.resources.limits == {"cpu": "250m", "memory": "256Mi"}
    assert container.security_context.allow_privilege_escalation is False
    assert container.security_context.capabilities.drop == ["ALL"]


def test_pod_service_rejects_invalid_pod_name_before_registry_check() -> None:
    core_api = MagicMock()
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    registry_client = MagicMock(spec=ContainerRegistryClient)
    service = PodService(settings, clients, registry_client)

    with pytest.raises(KubernetesOperationError, match="Pod name"):
        service.create_pod(
            "chatops-demo",
            "Invalid_Pod",
            "nginx:alpine",
        )

    registry_client.resolve.assert_not_called()
    core_api.create_namespaced_pod.assert_not_called()


def test_pod_service_rejects_disallowed_registry() -> None:
    core_api = MagicMock()
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    with pytest.raises(PermissionError, match="not allowed"):
        service.create_pod(
            "chatops-demo",
            "manual-test",
            "example/app:latest",
            "untrusted.example",
        )

    core_api.create_namespaced_pod.assert_not_called()


def test_pod_service_rejects_delete_in_disallowed_namespace() -> None:
    core_api = MagicMock()
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    with pytest.raises(PermissionError, match="kube-system"):
        service.delete_pod("kube-system", "coredns-123")

    core_api.delete_namespaced_pod.assert_not_called()


def test_pod_service_sorts_and_caps_pod_events() -> None:
    older = SimpleNamespace(
        type="Normal",
        reason="Scheduled",
        message="Assigned pod",
        count=1,
        first_timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        last_timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    newer = SimpleNamespace(
        type="Warning",
        reason="BackOff",
        message="Restarting container",
        count=2,
        first_timestamp=datetime(2026, 1, 2, 3, 5, 5, tzinfo=UTC),
        last_timestamp=datetime(2026, 1, 2, 3, 6, 5, tzinfo=UTC),
    )
    core_api = MagicMock()
    core_api.list_namespaced_event.return_value = SimpleNamespace(items=[older, newer])
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    result = service.get_pod_events("chatops-demo", "api-123", limit=999)

    assert [event.reason for event in result] == ["BackOff", "Scheduled"]
    assert core_api.list_namespaced_event.call_args.kwargs["limit"] == 100


def test_pod_service_normalizes_not_found_error() -> None:
    core_api = MagicMock()
    core_api.read_namespaced_pod.side_effect = ApiException(
        status=404,
        reason="Not Found",
    )
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    with pytest.raises(
        KubernetesResourceNotFoundError,
        match="chatops-demo/api-123 was not found",
    ):
        service.get_pod("chatops-demo", "api-123")


def test_pod_service_normalizes_access_denied_error() -> None:
    core_api = MagicMock()
    core_api.delete_namespaced_pod.side_effect = ApiException(
        status=403,
        reason="Forbidden",
    )
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    with pytest.raises(KubernetesAccessDeniedError, match="Access was denied"):
        service.delete_pod("chatops-demo", "api-123")


def test_pod_service_normalizes_transport_error() -> None:
    core_api = MagicMock()
    core_api.list_namespaced_pod.side_effect = HTTPError("connection failed")
    clients = MagicMock()
    clients.get_core_v1_api.return_value = core_api
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    service = PodService(settings, clients)

    with pytest.raises(
        KubernetesOperationError,
        match="Could not contact the Kubernetes API",
    ):
        service.get_pods("chatops-demo")
