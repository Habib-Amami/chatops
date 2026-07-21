"""Shared execution and exception translation for Kubernetes SDK calls."""

from collections.abc import Callable
from typing import TypeVar

from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import HTTPError

from app.platforms.kubernetes.errors import (
    KubernetesAccessDeniedError,
    KubernetesOperationError,
    KubernetesResourceNotFoundError,
)

T = TypeVar("T")


def execute_kubernetes_api_call(
    *,
    operation: str,
    resource: str,
    call: Callable[[], T],
) -> T:
    """Execute one Kubernetes SDK call behind a consistent error boundary.

    Args:
        operation: Human-readable action used in error messages, such as
            ``"read Pod"`` or ``"delete Deployment"``.
        resource: Exact namespace/resource description associated with the
            request, such as ``"demo-app/backend"``.
        call: Zero-argument callback that performs the Kubernetes SDK request.

    Returns:
        The original value returned by the SDK callback.

    Raises:
        KubernetesResourceNotFoundError: If the API returns HTTP 404.
        KubernetesAccessDeniedError: If the API returns HTTP 403.
        KubernetesOperationError: If the API returns another failure or the
            Kubernetes endpoint cannot be reached.

    Notes:
        Unexpected exceptions are not caught, so programming errors remain
        visible instead of being misreported as Kubernetes failures.
    """
    try:
        return call()
    except ApiException as error:
        status = getattr(error, "status", None)
        reason = getattr(error, "reason", None) or "Kubernetes API error"
        if status == 404:
            raise KubernetesResourceNotFoundError(
                f"{resource} was not found while attempting to {operation}"
            ) from error
        if status == 403:
            raise KubernetesAccessDeniedError(
                f"Access was denied while attempting to {operation} for {resource}"
            ) from error
        status_text = f" (status {status})" if status is not None else ""
        raise KubernetesOperationError(
            f"Could not {operation} for {resource}: {reason}{status_text}"
        ) from error
    except (HTTPError, TimeoutError, ConnectionError) as error:
        raise KubernetesOperationError(
            f"Could not contact the Kubernetes API while attempting to "
            f"{operation} for {resource}"
        ) from error
