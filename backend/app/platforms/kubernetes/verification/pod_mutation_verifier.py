"""Bounded readiness and deletion verification for standalone Pods."""

from collections.abc import Callable
from math import ceil
from time import sleep
from typing import Any

from app.platforms.kubernetes import (
    KubernetesOperationError,
    KubernetesResourceNotFoundError,
    execute_kubernetes_api_call,
)
from app.platforms.kubernetes.models import PodCreateResult, PodDeleteResult


class PodMutationVerifier:
    """Verify Pod mutations by polling without repeating the mutation itself.

    Creation and deletion requests are executed by ``PodService`` before this
    verifier is called. This class only performs read operations to observe the
    result, preventing retries from accidentally creating or deleting a Pod
    more than once.
    """

    def __init__(
        self,
        core_v1_api: Any,
        *,
        timeout_seconds: float,
        poll_seconds: float,
        sleep_function: Callable[[float], None] = sleep,
    ) -> None:
        """Configure bounded polling for Pod creation and deletion.

        Args:
            core_v1_api: Kubernetes ``CoreV1Api`` client used for status reads.
            timeout_seconds: Maximum approximate duration allowed for a
                verification operation.
            poll_seconds: Delay between consecutive Kubernetes API reads.
            sleep_function: Callable used to pause between reads. Tests can
                inject a replacement to avoid real delays.

        Notes:
            At least one verification attempt is always made. Configuration
            validation is responsible for ensuring that polling values are
            positive.
        """
        self._core_v1_api = core_v1_api
        self._poll_seconds = poll_seconds
        self._max_attempts = max(1, ceil(timeout_seconds / poll_seconds))
        self._sleep = sleep_function

    def verify_creation(
        self,
        *,
        namespace: str,
        pod_name: str,
        image: str,
        registry: str,
    ) -> PodCreateResult:
        """Wait for a created Pod to become ready or reach a terminal state.

        Args:
            namespace: Namespace containing the newly created Pod.
            pod_name: Exact name of the Pod whose status should be observed.
            image: Fully resolved container image used to create the Pod.
            registry: Registry associated with the resolved container image.

        Returns:
            A structured result describing one of the following outcomes:
            ready, succeeded, failed, readiness timeout, or verification error.

        Notes:
            A temporary 404 is treated as an expected creation delay and
            polling continues. Other Kubernetes operation errors are returned
            as ``verification_error`` results rather than raised. This method
            never submits another Pod creation request.
        """
        last_phase: str | None = None
        for attempt in range(self._max_attempts):
            try:
                pod = execute_kubernetes_api_call(
                    operation="verify Pod creation",
                    resource=f"{namespace}/{pod_name}",
                    call=lambda: self._core_v1_api.read_namespaced_pod_status(
                        name=pod_name,
                        namespace=namespace,
                    ),
                )
            except KubernetesResourceNotFoundError:
                pod = None
            except KubernetesOperationError as error:
                return PodCreateResult(
                    pod_name=pod_name,
                    namespace=namespace,
                    image=image,
                    registry=registry,
                    status="verification_error",
                    phase=last_phase,
                    verification_message=str(error),
                )

            status = getattr(pod, "status", None) if pod is not None else None
            last_phase = getattr(status, "phase", None)
            container_statuses = getattr(status, "container_statuses", None) or []
            ready = bool(container_statuses) and all(
                container_status.ready is True
                for container_status in container_statuses
            )
            if last_phase == "Running" and ready:
                return PodCreateResult(
                    pod_name=pod_name,
                    namespace=namespace,
                    image=image,
                    registry=registry,
                    status="ready",
                    phase=last_phase,
                    ready=True,
                )
            if last_phase == "Succeeded":
                return PodCreateResult(
                    pod_name=pod_name,
                    namespace=namespace,
                    image=image,
                    registry=registry,
                    status="succeeded",
                    phase=last_phase,
                )
            if last_phase == "Failed":
                return PodCreateResult(
                    pod_name=pod_name,
                    namespace=namespace,
                    image=image,
                    registry=registry,
                    status="failed",
                    phase=last_phase,
                    verification_message=(
                        getattr(status, "message", None)
                        or getattr(status, "reason", None)
                        or "Pod entered the Failed phase"
                    ),
                )
            self._sleep_before_next_attempt(attempt)

        return PodCreateResult(
            pod_name=pod_name,
            namespace=namespace,
            image=image,
            registry=registry,
            status="readiness_timeout",
            phase=last_phase,
            verification_message="Pod did not become ready before the timeout",
        )

    def verify_deletion(self, *, namespace: str, pod_name: str) -> PodDeleteResult:
        """Wait until the exact Pod name is no longer present.

        Args:
            namespace: Namespace from which the Pod was deleted.
            pod_name: Exact name of the Pod whose absence should be confirmed.

        Returns:
            A structured result confirming deletion, reporting a deletion
            timeout, or describing a verification error.

        Notes:
            An HTTP 404 confirms that the Pod is absent. Other Kubernetes
            operation errors are returned as ``verification_error`` results.
            This method only reads Pod state and never repeats the deletion.
        """
        for attempt in range(self._max_attempts):
            try:
                execute_kubernetes_api_call(
                    operation="verify Pod deletion",
                    resource=f"{namespace}/{pod_name}",
                    call=lambda: self._core_v1_api.read_namespaced_pod(
                        name=pod_name,
                        namespace=namespace,
                    ),
                )
            except KubernetesResourceNotFoundError:
                return PodDeleteResult(
                    pod_name=pod_name,
                    namespace=namespace,
                    status="deleted",
                    deleted=True,
                )
            except KubernetesOperationError as error:
                return PodDeleteResult(
                    pod_name=pod_name,
                    namespace=namespace,
                    status="verification_error",
                    deleted=False,
                    verification_message=str(error),
                )
            self._sleep_before_next_attempt(attempt)

        return PodDeleteResult(
            pod_name=pod_name,
            namespace=namespace,
            status="deletion_timeout",
            deleted=False,
            verification_message="Pod still existed when the deletion timeout expired",
        )

    def _sleep_before_next_attempt(self, attempt: int) -> None:
        """Pause after an attempt unless it was the final allowed attempt.

        Args:
            attempt: Zero-based index of the verification attempt that just
                completed.
        """
        if attempt < self._max_attempts - 1:
            self._sleep(self._poll_seconds)
