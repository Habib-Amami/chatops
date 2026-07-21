"""Agent tools backed by the Kubernetes Pod service."""

from collections.abc import Callable
from typing import TypeVar

from langchain.tools import BaseTool, tool
from langchain_core.tools import ToolException

from app.platforms.kubernetes import KubernetesOperationError
from app.platforms.kubernetes.services import PodService
from app.platforms.kubernetes.services.pod_service import (
    DEFAULT_LOG_TAIL_LINES,
    DEFAULT_POD_IMAGE,
)
from app.agent.tools.kubernetes.formatters import (
    INVALID_TOOL_INPUT_MESSAGE,
    format_pod_create_result,
    format_pod_delete_result,
    format_pod_description,
    format_pod_details,
    format_pod_diagnosis,
    format_pod_events,
    format_pod_list,
    format_pod_logs,
    format_tool_error,
)

T = TypeVar("T")


def _call_pod_service(call: Callable[[], T]) -> T:
    """Convert platform and policy failures into handled tool errors."""
    try:
        return call()
    except (KubernetesOperationError, PermissionError) as error:
        raise ToolException(str(error)) from error


def create_pod_tools(pod_service: PodService) -> list[BaseTool]:
    """Create pod tools bound to an initialized service."""

    @tool
    def get_kubernetes_pods(namespace: str) -> str:
        """Get pod health details in an allowed Kubernetes namespace.

        Use this when a user asks which pods exist, whether pods are ready,
        where pods are scheduled, or how often their containers restarted.
        """
        pods = _call_pod_service(lambda: pod_service.get_pods(namespace))
        return format_pod_list(pods, namespace)

    @tool
    def get_kubernetes_pod(namespace: str, pod_name: str) -> str:
        """Get detailed status for one Pod in an allowed namespace.

        Use this when a user asks about a specific pod's readiness, containers,
        labels, node placement, restart counts, or conditions.
        """
        pod = _call_pod_service(lambda: pod_service.get_pod(namespace, pod_name))
        return format_pod_details(pod)

    @tool
    def get_kubernetes_pod_logs(
        namespace: str,
        pod_name: str,
        container: str | None = None,
        tail_lines: int = DEFAULT_LOG_TAIL_LINES,
        previous: bool = False,
        since_seconds: int | None = None,
    ) -> str:
        """Get bounded current or previous logs for a Pod container.

        Use this when a user asks why a pod or container is failing, crashing,
        or producing errors. Set previous=true after a container restart or
        CrashLoopBackOff. Use since_seconds for a bounded incident time window.
        Output is truncated when necessary to protect the model context.
        """
        logs = _call_pod_service(
            lambda: pod_service.get_pod_logs(
                namespace,
                pod_name,
                container=container,
                tail_lines=tail_lines,
                previous=previous,
                since_seconds=since_seconds,
            )
        )
        return format_pod_logs(
            logs,
            pod_name,
            namespace,
            previous=previous,
        )

    @tool
    def get_kubernetes_pod_events(
        pod_name: str,
        namespace: str,
        limit: int = 20,
    ) -> str:
        """Get Kubernetes events for a Pod in an allowed namespace.

        Use this when a Pod is Pending, cannot pull an image, has no logs, or
        when Kubernetes scheduling and lifecycle messages are needed.
        """
        events = _call_pod_service(
            lambda: pod_service.get_pod_events(
                namespace,
                pod_name,
                limit=limit,
            )
        )
        return format_pod_events(events, pod_name, namespace)

    @tool
    def diagnose_kubernetes_pod_status(
        pod_name: str,
        namespace: str,
    ) -> str:
        """Inspect container states for a Pod when logs are unavailable.

        Use this to see Waiting, Running, and Terminated states together with
        restart counts and Kubernetes-provided reasons such as OOMKilled or
        ImagePullBackOff.
        """
        diagnosis = _call_pod_service(
            lambda: pod_service.diagnose_pod_status(namespace, pod_name)
        )
        return format_pod_diagnosis(diagnosis)

    @tool
    def create_kubernetes_pod(
        name: str,
        namespace: str,
        image: str = DEFAULT_POD_IMAGE,
        registry: str | None = None,
    ) -> str:
        """Create one standalone test Pod after explicit user approval.

        The Pod has no Deployment, StatefulSet, or other workload controller,
        so deleting it later will not cause Kubernetes to recreate it. The
        image may be any public repository[:tag] on a configured registry.
        Docker Hub is used when registry is omitted. The image manifest is
        verified before creation; private images are not supported yet.
        """
        result = _call_pod_service(
            lambda: pod_service.create_pod(namespace, name, image, registry)
        )
        return format_pod_create_result(result)

    @tool
    def delete_kubernetes_pod(
        name: str,
        namespace: str,
    ) -> str:
        """Delete one Pod after the user explicitly requests that mutation.

        A Pod controlled by a Deployment, StatefulSet, or other workload may
        be recreated automatically by its controller.
        """
        result = _call_pod_service(lambda: pod_service.delete_pod(namespace, name))
        return format_pod_delete_result(result)

    @tool
    def describe_kubernetes_pod(namespace: str, pod_name: str) -> str:
        """Describe one Pod using details and related Kubernetes events.

        Use this when a user asks what is wrong with a pod, why it is pending,
        why it is not ready, or asks for a describe-style diagnosis.
        """
        pod = _call_pod_service(lambda: pod_service.get_pod(namespace, pod_name))
        events = _call_pod_service(
            lambda: pod_service.get_pod_events(namespace, pod_name)
        )
        return format_pod_description(pod, events)

    tools = [
        get_kubernetes_pods,
        get_kubernetes_pod,
        get_kubernetes_pod_logs,
        get_kubernetes_pod_events,
        diagnose_kubernetes_pod_status,
        create_kubernetes_pod,
        delete_kubernetes_pod,
        describe_kubernetes_pod,
    ]
    for pod_tool in tools:
        pod_tool.handle_tool_error = format_tool_error
        pod_tool.handle_validation_error = INVALID_TOOL_INPUT_MESSAGE
    return tools
