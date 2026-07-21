"""Namespace-scoped Kubernetes Pod operations."""

from typing import cast

from kubernetes import client as kubernetes_client
from urllib3.response import HTTPResponse

from app.core import Settings
from app.platforms.kubernetes import (
    KubernetesClientFactory,
    KubernetesResourceNotFoundError,
    execute_kubernetes_api_call,
    validate_kubernetes_namespace,
    validate_kubernetes_pod_name,
)
from app.platforms.kubernetes.models import (
    PodCreateResult,
    PodDeleteResult,
    PodDetails,
    PodEventSummary,
    PodStatusDiagnosis,
    PodSummary,
)
from app.platforms.kubernetes.mappers import (
    build_pod_details,
    build_pod_events,
    build_pod_status_diagnosis,
    build_pod_summary,
)
from app.platforms.kubernetes.registry import ContainerRegistryClient
from app.platforms.kubernetes.verification import PodMutationVerifier

DEFAULT_LOG_TAIL_LINES = 50
DEFAULT_POD_IMAGE = "nginxinc/nginx-unprivileged:alpine"
MAX_LOG_TAIL_LINES = 200
POD_CPU_REQUEST = "50m"
POD_CPU_LIMIT = "250m"
POD_MEMORY_REQUEST = "64Mi"
POD_MEMORY_LIMIT = "256Mi"


class PodService:
    """Provide namespace-scoped Pod inspection and approved mutations."""

    def __init__(
        self,
        settings: Settings,
        clients: KubernetesClientFactory,
        registry_client: ContainerRegistryClient | None = None,
        mutation_verifier: PodMutationVerifier | None = None,
    ) -> None:
        self._allowed_namespaces = frozenset(settings.kubernetes_allowed_namespaces)
        self._core_v1_api = clients.get_core_v1_api()
        self._registry_client = registry_client or ContainerRegistryClient(
            allowed_registries=settings.kubernetes_allowed_pod_registries,
            default_registry=settings.kubernetes_default_pod_registry,
            timeout_seconds=settings.kubernetes_registry_check_timeout_seconds,
        )
        self._mutation_verifier = mutation_verifier or PodMutationVerifier(
            self._core_v1_api,
            timeout_seconds=settings.kubernetes_pod_verification_timeout_seconds,
            poll_seconds=settings.kubernetes_pod_verification_poll_seconds,
        )

    def get_pods(self, namespace: str) -> list[PodSummary]:
        """Get Pod health information in one explicitly allowed namespace."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        raw_response = execute_kubernetes_api_call(
            operation="list Pods",
            resource=f"namespace {namespace!r}",
            call=lambda: self._core_v1_api.list_namespaced_pod(namespace=namespace),
        )
        if raw_response is None:
            return []

        response = cast(kubernetes_client.V1PodList, raw_response)
        pods: list[PodSummary] = []

        for pod in response.items or []:
            summary = build_pod_summary(pod, namespace)
            if summary is None:
                continue
            pods.append(summary)

        return pods

    def get_pod(self, namespace: str, pod_name: str) -> PodDetails:
        """Get detailed read-only information for one Pod."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        validate_kubernetes_pod_name(pod_name)

        raw_pod = execute_kubernetes_api_call(
            operation="get Pod",
            resource=f"{namespace}/{pod_name}",
            call=lambda: self._core_v1_api.read_namespaced_pod(
                name=pod_name,
                namespace=namespace,
            ),
        )
        if raw_pod is None:
            raise KubernetesResourceNotFoundError(
                f"Pod {namespace}/{pod_name} was not found"
            )

        pod = cast(kubernetes_client.V1Pod, raw_pod)
        details = build_pod_details(pod, namespace)
        if details is None:
            raise KubernetesResourceNotFoundError(
                f"Pod {namespace}/{pod_name} was not found"
            )
        return details

    def get_pod_logs(
        self,
        namespace: str,
        pod_name: str,
        *,
        container: str | None = None,
        tail_lines: int = DEFAULT_LOG_TAIL_LINES,
        previous: bool = False,
        since_seconds: int | None = None,
    ) -> str:
        """Get bounded, decoded current or previous logs for one container."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        validate_kubernetes_pod_name(pod_name)

        safe_tail_lines = min(max(tail_lines, 1), MAX_LOG_TAIL_LINES)
        safe_since_seconds = (
            min(max(since_seconds, 1), 86_400) if since_seconds is not None else None
        )
        logs = execute_kubernetes_api_call(
            operation="get previous Pod logs" if previous else "get Pod logs",
            resource=f"{namespace}/{pod_name}",
            call=lambda: self._core_v1_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                tail_lines=safe_tail_lines,
                timestamps=True,
                previous=previous,
                since_seconds=safe_since_seconds,
                _preload_content=False,
            ),
        )
        if isinstance(logs, HTTPResponse):
            try:
                return logs.data.decode("utf-8", errors="replace")
            finally:
                logs.release_conn()
        if isinstance(logs, (bytes, bytearray)):
            text = bytes(logs).decode("utf-8", errors="replace")
        else:
            text = str(logs or "")
        return text

    def get_pod_events(
        self,
        namespace: str,
        pod_name: str,
        *,
        limit: int = 20,
    ) -> list[PodEventSummary]:
        """Get a bounded, newest-first list of events related to one Pod."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        validate_kubernetes_pod_name(pod_name)

        safe_limit = min(max(limit, 1), 100)
        raw_response = execute_kubernetes_api_call(
            operation="list Pod events",
            resource=f"{namespace}/{pod_name}",
            call=lambda: self._core_v1_api.list_namespaced_event(
                namespace=namespace,
                field_selector=(
                    f"involvedObject.name={pod_name},involvedObject.kind=Pod"
                ),
                limit=safe_limit,
            ),
        )
        if raw_response is None:
            return []

        response = cast(kubernetes_client.CoreV1EventList, raw_response)
        return build_pod_events(response.items or [], safe_limit)

    def diagnose_pod_status(
        self,
        namespace: str,
        pod_name: str,
    ) -> PodStatusDiagnosis:
        """Get current container states for a Pod that may not have logs."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        validate_kubernetes_pod_name(pod_name)

        raw_pod = execute_kubernetes_api_call(
            operation="get Pod status",
            resource=f"{namespace}/{pod_name}",
            call=lambda: self._core_v1_api.read_namespaced_pod_status(
                name=pod_name,
                namespace=namespace,
            ),
        )
        if raw_pod is None:
            raise KubernetesResourceNotFoundError(
                f"Pod {namespace}/{pod_name} was not found"
            )

        pod = cast(kubernetes_client.V1Pod, raw_pod)
        return build_pod_status_diagnosis(pod, namespace, pod_name)

    def delete_pod(
        self,
        namespace: str,
        pod_name: str,
    ) -> PodDeleteResult:
        """Request deletion of one Pod in an explicitly allowed namespace."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        validate_kubernetes_pod_name(pod_name)

        execute_kubernetes_api_call(
            operation="delete Pod",
            resource=f"{namespace}/{pod_name}",
            call=lambda: self._core_v1_api.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace,
            ),
        )
        return self._mutation_verifier.verify_deletion(
            namespace=namespace,
            pod_name=pod_name,
        )

    def create_pod(
        self,
        namespace: str,
        pod_name: str,
        image: str,
        registry: str | None = None,
    ) -> PodCreateResult:
        """Verify and create one standalone Pod without a workload controller."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        validate_kubernetes_pod_name(pod_name)
        image_reference = self._registry_client.resolve(image, registry)
        self._registry_client.verify_exists(image_reference)

        pod = kubernetes_client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=kubernetes_client.V1ObjectMeta(
                name=pod_name,
                labels={
                    "app.kubernetes.io/managed-by": "chatops",
                    "chatops-purpose": "standalone-test",
                },
            ),
            spec=kubernetes_client.V1PodSpec(
                automount_service_account_token=False,
                containers=[
                    kubernetes_client.V1Container(
                        name="main",
                        image=image_reference.pull_reference,
                        image_pull_policy="IfNotPresent",
                        resources=kubernetes_client.V1ResourceRequirements(
                            requests={
                                "cpu": POD_CPU_REQUEST,
                                "memory": POD_MEMORY_REQUEST,
                            },
                            limits={
                                "cpu": POD_CPU_LIMIT,
                                "memory": POD_MEMORY_LIMIT,
                            },
                        ),
                        security_context=kubernetes_client.V1SecurityContext(
                            allow_privilege_escalation=False,
                            capabilities=kubernetes_client.V1Capabilities(drop=["ALL"]),
                        ),
                    )
                ],
                restart_policy="Never",
                security_context=kubernetes_client.V1PodSecurityContext(
                    seccomp_profile=kubernetes_client.V1SeccompProfile(
                        type="RuntimeDefault"
                    )
                ),
                termination_grace_period_seconds=5,
            ),
        )
        execute_kubernetes_api_call(
            operation="create Pod",
            resource=f"{namespace}/{pod_name}",
            call=lambda: self._core_v1_api.create_namespaced_pod(
                namespace=namespace,
                body=pod,
            ),
        )
        return self._mutation_verifier.verify_creation(
            namespace=namespace,
            pod_name=pod_name,
            image=image_reference.pull_reference,
            registry=image_reference.registry,
        )
