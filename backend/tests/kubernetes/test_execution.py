import pytest
from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError

from app.platforms.kubernetes import (
    KubernetesAccessDeniedError,
    KubernetesOperationError,
    KubernetesResourceNotFoundError,
    execute_kubernetes_api_call,
)


def test_execute_kubernetes_api_call_returns_successful_result() -> None:
    result = execute_kubernetes_api_call(
        operation="read Pod",
        resource="demo-app/api-123",
        call=lambda: {"status": "ok"},
    )

    assert result == {"status": "ok"}


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (404, KubernetesResourceNotFoundError),
        (403, KubernetesAccessDeniedError),
        (500, KubernetesOperationError),
    ],
)
def test_execute_kubernetes_api_call_translates_api_errors(
    status: int,
    expected_error: type[KubernetesOperationError],
) -> None:
    def failing_call() -> None:
        raise ApiException(status=status, reason="API failure")

    with pytest.raises(expected_error, match="demo-app/api-123"):
        execute_kubernetes_api_call(
            operation="read Pod",
            resource="demo-app/api-123",
            call=failing_call,
        )


def test_execute_kubernetes_api_call_translates_transport_errors() -> None:
    def failing_call() -> None:
        raise HTTPError("connection failed")

    with pytest.raises(KubernetesOperationError, match="Could not contact"):
        execute_kubernetes_api_call(
            operation="read Pod",
            resource="demo-app/api-123",
            call=failing_call,
        )
