"""Agent tools backed by the Kubernetes Pod service."""

from langchain.tools import BaseTool, tool

from app.platforms.kubernetes.services import PodService


def create_pod_tools(pod_service: PodService) -> list[BaseTool]:
    """Create pod tools bound to an initialized service."""

    @tool
    def list_kubernetes_pods(namespace: str) -> list[dict[str, object]]:
        """List pod health details in an allowed Kubernetes namespace.

        Use this when a user asks which pods exist, whether pods are ready,
        where pods are scheduled, or how often their containers restarted.
        """
        pods = pod_service.list_pods(namespace)
        return [pod.model_dump(mode="json") for pod in pods]

    return [list_kubernetes_pods]
