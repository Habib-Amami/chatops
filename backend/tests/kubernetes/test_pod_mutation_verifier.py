from types import SimpleNamespace
from unittest.mock import MagicMock

from kubernetes.client.exceptions import ApiException

from app.platforms.kubernetes.verification import PodMutationVerifier


def _verifier(core_v1_api: MagicMock) -> PodMutationVerifier:
    return PodMutationVerifier(
        core_v1_api,
        timeout_seconds=0.02,
        poll_seconds=0.01,
        sleep_function=MagicMock(),
    )


def test_pod_creation_verification_reports_ready() -> None:
    core_v1_api = MagicMock()
    core_v1_api.read_namespaced_pod_status.return_value = SimpleNamespace(
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[SimpleNamespace(ready=True)],
        )
    )

    result = _verifier(core_v1_api).verify_creation(
        namespace="chatops-demo",
        pod_name="manual-test",
        image="docker.io/example/app:v1",
        registry="docker.io",
    )

    assert result.status == "ready"
    assert result.ready is True
    assert result.phase == "Running"


def test_pod_creation_verification_reports_terminal_failure() -> None:
    core_v1_api = MagicMock()
    core_v1_api.read_namespaced_pod_status.return_value = SimpleNamespace(
        status=SimpleNamespace(
            phase="Failed",
            container_statuses=[SimpleNamespace(ready=False)],
            reason="Error",
            message="container exited",
        )
    )

    result = _verifier(core_v1_api).verify_creation(
        namespace="chatops-demo",
        pod_name="manual-test",
        image="docker.io/example/app:v1",
        registry="docker.io",
    )

    assert result.status == "failed"
    assert result.ready is False
    assert result.verification_message == "container exited"


def test_pod_creation_verification_times_out_without_repeating_creation() -> None:
    core_v1_api = MagicMock()
    core_v1_api.read_namespaced_pod_status.return_value = SimpleNamespace(
        status=SimpleNamespace(phase="Pending", container_statuses=[])
    )

    result = _verifier(core_v1_api).verify_creation(
        namespace="chatops-demo",
        pod_name="manual-test",
        image="docker.io/example/app:v1",
        registry="docker.io",
    )

    assert result.status == "readiness_timeout"
    assert result.phase == "Pending"
    assert core_v1_api.read_namespaced_pod_status.call_count == 2


def test_pod_deletion_verification_confirms_absence() -> None:
    core_v1_api = MagicMock()
    core_v1_api.read_namespaced_pod.side_effect = ApiException(
        status=404,
        reason="Not Found",
    )

    result = _verifier(core_v1_api).verify_deletion(
        namespace="chatops-demo",
        pod_name="manual-test",
    )

    assert result.status == "deleted"
    assert result.deleted is True


def test_pod_deletion_verification_reports_timeout() -> None:
    core_v1_api = MagicMock()
    core_v1_api.read_namespaced_pod.return_value = SimpleNamespace()

    result = _verifier(core_v1_api).verify_deletion(
        namespace="chatops-demo",
        pod_name="manual-test",
    )

    assert result.status == "deletion_timeout"
    assert result.deleted is False
    assert core_v1_api.read_namespaced_pod.call_count == 2
