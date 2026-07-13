"""Read-only Kubernetes Pod operations."""

from typing import cast

from kubernetes import client as kubernetes_client
from pydantic import BaseModel

from app.core import Settings
from app.platforms.kubernetes import (
    KubernetesClientFactory,
    validate_kubernetes_namespace,
)


class PodSummary(BaseModel):
    """Small, agent-safe representation of a Kubernetes Pod."""

    name: str
    namespace: str
    phase: str | None
    ready: bool
    restart_count: int
    node_name: str | None
    pod_ip: str | None
    images: list[str]


class PodContainerSummary(BaseModel):
    """Small, agent-safe representation of one Pod container."""

    name: str
    image: str | None
    ready: bool
    restart_count: int


class PodConditionSummary(BaseModel):
    """Small, agent-safe representation of one Pod condition."""

    type: str
    status: str | None
    reason: str | None
    message: str | None


class PodDetails(PodSummary):
    """Detailed, read-only Pod information for diagnosis."""

    labels: dict[str, str]
    created_at: str | None
    containers: list[PodContainerSummary]
    conditions: list[PodConditionSummary]


class PodEventSummary(BaseModel):
    """Small, agent-safe representation of one Kubernetes event."""

    type: str | None
    reason: str | None
    message: str | None
    count: int | None
    first_timestamp: str | None
    last_timestamp: str | None


class PodService:
    """Provide namespace-scoped, read-only Pod operations."""

    def __init__(
        self,
        settings: Settings,
        clients: KubernetesClientFactory,
    ) -> None:
        self._allowed_namespaces = frozenset(
            settings.kubernetes_allowed_namespaces
        )
        self._core_v1_api = clients.get_core_v1_api()

    def get_pods(self, namespace: str) -> list[PodSummary]:
        """Get Pod health information in one explicitly allowed namespace."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        raw_response = self._core_v1_api.list_namespaced_pod(namespace=namespace)
        if raw_response is None:
            return []

        response = cast(kubernetes_client.V1PodList, raw_response)
        pods: list[PodSummary] = []

        for pod in response.items or []:
            summary = self._build_pod_summary(pod, namespace)
            if summary is None:
                continue
            pods.append(summary)

        return pods

    def get_pod(self, namespace: str, pod_name: str) -> PodDetails:
        """Get detailed read-only information for one Pod."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        raw_pod = self._core_v1_api.read_namespaced_pod(
            name=pod_name,
            namespace=namespace,
        )
        if raw_pod is None:
            raise LookupError(f"Pod {pod_name!r} was not found")

        pod = cast(kubernetes_client.V1Pod, raw_pod)
        summary = self._build_pod_summary(pod, namespace)
        if summary is None:
            raise LookupError(f"Pod {pod_name!r} was not found")

        metadata = pod.metadata
        spec = pod.spec
        status = pod.status
        container_statuses = (
            status.container_statuses
            if status is not None and status.container_statuses is not None
            else []
        )
        conditions = (
            status.conditions
            if status is not None and status.conditions is not None
            else []
        )

        return PodDetails(
            **summary.model_dump(),
            labels=dict(metadata.labels or {}) if metadata is not None else {},
            created_at=(
                metadata.creation_timestamp.isoformat()
                if metadata is not None
                and metadata.creation_timestamp is not None
                else None
            ),
            containers=[
                PodContainerSummary(
                    name=container_status.name,
                    image=container_status.image,
                    ready=container_status.ready is True,
                    restart_count=container_status.restart_count or 0,
                )
                for container_status in container_statuses
                if container_status.name is not None
            ],
            conditions=[
                PodConditionSummary(
                    type=condition.type,
                    status=condition.status,
                    reason=condition.reason,
                    message=condition.message,
                )
                for condition in conditions
                if condition.type is not None
            ],
        )

    def get_pod_logs(
        self,
        namespace: str,
        pod_name: str,
        *,
        container: str | None = None,
        tail_lines: int = 100,
    ) -> str:
        """Get recent logs for one Pod, limited to a safe tail size."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        safe_tail_lines = min(max(tail_lines, 1), 500)
        logs = self._core_v1_api.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=safe_tail_lines,
            timestamps=True,
        )
        return str(logs or "")

    def get_pod_events(
        self,
        namespace: str,
        pod_name: str,
    ) -> list[PodEventSummary]:
        """Get Kubernetes events related to one Pod."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        raw_response = self._core_v1_api.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.name={pod_name},involvedObject.kind=Pod",
        )
        if raw_response is None:
            return []

        response = cast(kubernetes_client.CoreV1EventList, raw_response)
        return [
            PodEventSummary(
                type=event.type,
                reason=event.reason,
                message=event.message,
                count=event.count,
                first_timestamp=(
                    event.first_timestamp.isoformat()
                    if event.first_timestamp is not None
                    else None
                ),
                last_timestamp=(
                    event.last_timestamp.isoformat()
                    if event.last_timestamp is not None
                    else None
                ),
            )
            for event in response.items or []
        ]

    def _build_pod_summary(
        self,
        pod: kubernetes_client.V1Pod,
        namespace: str,
    ) -> PodSummary | None:
        """Build the shared compact Pod summary shape."""
        metadata = pod.metadata
        if metadata is None or metadata.name is None:
            return None

        spec = pod.spec
        status = pod.status
        containers = (
            spec.containers
            if spec is not None and spec.containers is not None
            else []
        )
        container_statuses = (
            status.container_statuses
            if status is not None and status.container_statuses is not None
            else []
        )

        return PodSummary(
            name=metadata.name,
            namespace=metadata.namespace or namespace,
            phase=status.phase if status is not None else None,
            ready=bool(container_statuses)
            and all(
                container_status.ready is True
                for container_status in container_statuses
            ),
            restart_count=sum(
                container_status.restart_count or 0
                for container_status in container_statuses
            ),
            node_name=spec.node_name if spec is not None else None,
            pod_ip=status.pod_ip if status is not None else None,
            images=[
                container.image
                for container in containers
                if container.image is not None
            ],
        )
