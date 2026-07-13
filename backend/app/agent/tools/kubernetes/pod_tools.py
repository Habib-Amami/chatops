"""Agent tools backed by the Kubernetes Pod service."""

from langchain.tools import BaseTool, tool

from app.platforms.kubernetes.services import (
    PodDetails,
    PodEventSummary,
    PodService,
    PodSummary,
)


def _format_pod_summary(pod: PodSummary) -> str:
    """Format one Pod as a compact observation for the agent."""
    readiness = "ready" if pod.ready else "not ready"
    phase = pod.phase or "unknown phase"
    node = pod.node_name or "unknown node"
    pod_ip = pod.pod_ip or "unknown IP"
    images = ", ".join(pod.images) if pod.images else "unknown image"

    return (
        f"- {pod.name}: {phase}, {readiness}, "
        f"restarts={pod.restart_count}, node={node}, ip={pod_ip}, "
        f"images={images}"
    )


def _format_pod_details(pod: PodDetails) -> str:
    """Format detailed Pod information as an agent-friendly observation."""
    labels = (
        ", ".join(f"{key}={value}" for key, value in sorted(pod.labels.items()))
        if pod.labels
        else "none"
    )
    containers = (
        "\n".join(
            "- "
            f"{container.name}: image={container.image or 'unknown image'}, "
            f"{'ready' if container.ready else 'not ready'}, "
            f"restarts={container.restart_count}"
            for container in pod.containers
        )
        if pod.containers
        else "- no container statuses reported"
    )
    conditions = (
        "\n".join(
            "- "
            f"{condition.type}: status={condition.status or 'unknown'}, "
            f"reason={condition.reason or 'none'}, "
            f"message={condition.message or 'none'}"
            for condition in pod.conditions
        )
        if pod.conditions
        else "- no conditions reported"
    )

    return (
        f"Pod {pod.name!r} in namespace {pod.namespace!r}:\n"
        f"Phase: {pod.phase or 'unknown'}\n"
        f"Ready: {'yes' if pod.ready else 'no'}\n"
        f"Restarts: {pod.restart_count}\n"
        f"Node: {pod.node_name or 'unknown'}\n"
        f"IP: {pod.pod_ip or 'unknown'}\n"
        f"Created at: {pod.created_at or 'unknown'}\n"
        f"Labels: {labels}\n"
        f"Containers:\n{containers}\n"
        f"Conditions:\n{conditions}"
    )


def _format_pod_event(event: PodEventSummary) -> str:
    """Format one Kubernetes event as a compact observation."""
    event_type = event.type or "Unknown"
    reason = event.reason or "Unknown"
    message = event.message or "No message"
    count = event.count if event.count is not None else "unknown"
    last_seen = event.last_timestamp or "unknown"
    return (
        f"- {event_type} {reason}: {message} "
        f"(count={count}, last_seen={last_seen})"
    )


def create_pod_tools(pod_service: PodService) -> list[BaseTool]:
    """Create pod tools bound to an initialized service."""

    @tool
    def get_kubernetes_pods(namespace: str) -> str:
        """Get pod health details in an allowed Kubernetes namespace.

        Use this when a user asks which pods exist, whether pods are ready,
        where pods are scheduled, or how often their containers restarted.
        """
        pods = pod_service.get_pods(namespace)
        if not pods:
            return f"No pods were found in namespace {namespace!r}."

        formatted_pods = "\n".join(_format_pod_summary(pod) for pod in pods)
        return f"Pods in namespace {namespace!r}:\n{formatted_pods}"

    @tool
    def get_kubernetes_pod(namespace: str, pod_name: str) -> str:
        """Get detailed status for one Pod in an allowed namespace.

        Use this when a user asks about a specific pod's readiness, containers,
        labels, node placement, restart counts, or conditions.
        """
        pod = pod_service.get_pod(namespace, pod_name)
        return _format_pod_details(pod)

    @tool
    def get_kubernetes_pod_logs(
        namespace: str,
        pod_name: str,
        container: str | None = None,
        tail_lines: int = 100,
    ) -> str:
        """Get recent logs for one Pod in an allowed namespace.

        Use this when a user asks why a pod or container is failing, crashing,
        or producing errors. Prefer small tail sizes.
        """
        logs = pod_service.get_pod_logs(
            namespace,
            pod_name,
            container=container,
            tail_lines=tail_lines,
        )
        if not logs.strip():
            return (
                f"No recent logs were returned for pod {pod_name!r} "
                f"in namespace {namespace!r}."
            )
        return (
            f"Recent logs for pod {pod_name!r} "
            f"in namespace {namespace!r}:\n{logs.strip()}"
        )

    @tool
    def describe_kubernetes_pod(namespace: str, pod_name: str) -> str:
        """Describe one Pod using details and related Kubernetes events.

        Use this when a user asks what is wrong with a pod, why it is pending,
        why it is not ready, or asks for a describe-style diagnosis.
        """
        pod = pod_service.get_pod(namespace, pod_name)
        events = pod_service.get_pod_events(namespace, pod_name)
        formatted_events = (
            "\n".join(_format_pod_event(event) for event in events)
            if events
            else "- no events reported"
        )
        return f"{_format_pod_details(pod)}\nEvents:\n{formatted_events}"

    return [
        get_kubernetes_pods,
        get_kubernetes_pod,
        get_kubernetes_pod_logs,
        describe_kubernetes_pod,
    ]
