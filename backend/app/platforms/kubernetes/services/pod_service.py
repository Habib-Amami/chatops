"""Read-only Kubernetes Pod operations."""

from typing import cast

from kubernetes import client as kubernetes_client
from pydantic import BaseModel

from app.core import Settings
from app.platforms.kubernetes import KubernetesClientFactory


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

    def list_pods(self, namespace: str) -> list[PodSummary]:
        """List pod health information in one explicitly allowed namespace."""
        if namespace not in self._allowed_namespaces:
            raise PermissionError(f"Namespace {namespace!r} is not allowed")

        raw_response = self._core_v1_api.list_namespaced_pod(namespace=namespace)
        if raw_response is None:
            return []

        response = cast(kubernetes_client.V1PodList, raw_response)
        pods: list[PodSummary] = []

        for pod in response.items or []:
            metadata = pod.metadata
            if metadata is None or metadata.name is None:
                continue

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

            pods.append(
                PodSummary(
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
            )

        return pods