"""Agent tools for active Kubernetes Deployment orchestration."""

from collections.abc import Callable
from typing import Any, TypeVar

from langchain.tools import BaseTool, tool
from langchain_core.tools import ToolException

from app.platforms.kubernetes import KubernetesOperationError
from app.platforms.kubernetes.services.deployment_manager_service import (
    DeploymentManagerService,
)

T = TypeVar("T")

INVALID_DEPLOYMENT_TOOL_INPUT_MESSAGE = (
    "Kubernetes deployment operation could not run because required parameters "
    "were missing or invalid. Do not retry until the deployment name, namespace, "
    "and any operation-specific values are known."
)


def _call_deployment_service(call: Callable[[], T]) -> T:
    """Convert platform and policy failures into handled tool errors."""
    try:
        return call()
    except (KubernetesOperationError, PermissionError) as error:
        raise ToolException(str(error)) from error


def _format_deployment_tool_error(error: ToolException) -> str:
    return f"Kubernetes deployment operation failed: {error}"


def create_deployment_manager_tools(
    deployment_manager_service: DeploymentManagerService,
) -> list[BaseTool]:
    """Create deployment orchestration tools bound to the management service."""

    @tool
    def list_kubernetes_deployments(
        namespace: str,
    ) -> list[dict]:
        """List all Deployments in a Kubernetes namespace with their replica counts and health.

        USE THIS when the user asks to:
        - 'list deployments in <namespace>'
        - 'show all deployments'
        - 'what deployments are running in <namespace>?'

        Args:
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.list_deployments(
                namespace=namespace,
            )
        )

    @tool
    def get_kubernetes_deployment(
        name: str,
        namespace: str,
    ) -> dict:
        """Get full details for a single Kubernetes Deployment.

        USE THIS when the user asks to:
        - 'get deployment <name> in <namespace>'
        - 'describe deployment <name>'
        - 'show details of <name> deployment'

        Returns metadata, replica counts, container images, strategy, and conditions.

        Args:
            name:      Deployment name (e.g. 'backend').
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.get_deployment(
                name=name,
                namespace=namespace,
            )
        )

    @tool
    def get_kubernetes_deployment_status(
        name: str,
        namespace: str,
    ) -> dict:
        """Get the rollout health status of a Kubernetes Deployment.

        USE THIS when the user asks:
        - 'is deployment <name> healthy?'
        - 'what is the status of <name>?'
        - 'is the rollout complete for <name>?'

        Returns rollout_state (complete / in_progress / degraded / unknown),
        replica counts, and rollout conditions.

        Args:
            name:      Deployment name.
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.get_deployment_status(
                name=name,
                namespace=namespace,
            )
        )

    @tool
    def get_kubernetes_deployment_history(
        name: str,
        namespace: str,
    ) -> dict:
        """Get the revision history for a Kubernetes Deployment.

        USE THIS when the user asks:
        - 'show rollout history for <name>'
        - 'what revisions exist for <name>?'
        - 'list versions of <name> deployment'

        Returns all ReplicaSet revisions sorted oldest-first, each with its
        container images and change-cause annotation.

        Args:
            name:      Deployment name.
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.get_deployment_history(
                name=name,
                namespace=namespace,
            )
        )

    @tool
    def create_kubernetes_deployment(
        name: str,
        namespace: str,
        image: str,
        replicas: int = 1,
        container_name: str | None = None,
        port: int | None = None,
    ) -> dict:
        """Create a new Kubernetes Deployment in an allowed namespace.

        USE THIS when the user asks to:
        - 'create a deployment named <name> with image <image> in <namespace>'
        - 'deploy <image> as <name> in <namespace>'
        - 'launch a new deployment'

        Builds a secure, minimal Deployment manifest with resource limits
        and a RollingUpdate strategy.

        Args:
            name:           Deployment name.
            namespace:      Kubernetes namespace (must be in the allowed list).
            image:          Container image reference (e.g. 'nginx:alpine').
            replicas:       Number of initial replicas (default 1).
            container_name: Container name — defaults to the deployment name.
            port:           Optional container port to expose.
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.create_deployment(
                name=name,
                namespace=namespace,
                image=image,
                replicas=replicas,
                container_name=container_name,
                port=port,
            )
        )

    @tool
    def delete_kubernetes_deployment(
        name: str,
        namespace: str,
    ) -> dict:
        """Delete a Kubernetes Deployment from an allowed namespace.

        USE THIS when the user asks to:
        - 'delete deployment <name> in <namespace>'
        - 'remove deployment <name>'
        - 'tear down <name> in <namespace>'

        Kubernetes will cascade-delete the owned ReplicaSets and Pods.

        Args:
            name:      Deployment name.
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.delete_deployment(
                name=name,
                namespace=namespace,
            )
        )

    @tool
    def scale_kubernetes_deployment(
        name: str,
        namespace: str,
        replicas: int,
    ) -> dict[str, Any]:
        """Scale a Kubernetes deployment dynamically to a desired number of replicas.

        Use this when the user asks to scale up/down, resize, or change the replica
        count of a deployment (e.g., 'scale deployment frontend to 3 replicas' or
        'set replicas for database to 1').
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.scale_deployment(
                name=name,
                namespace=namespace,
                replicas=replicas,
            )
        )

    @tool
    def restart_kubernetes_deployment(
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Trigger a rolling restart of a Kubernetes deployment.

        Use this to replace or restart failed pods, clear stuck states, or refresh
        configuration by performing a rollout restart (equivalent to 'kubectl rollout restart').
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.restart_deployment(
                name=name,
                namespace=namespace,
            )
        )

    @tool
    def update_kubernetes_deployment_image(
        name: str,
        namespace: str,
        container_name: str,
        new_image: str,
    ) -> dict[str, Any]:
        """Update a container image inside a Kubernetes deployment.

        Use this to perform rolling updates of container images (e.g., 'update the backend
        container image to my-image:v2' or 'upgrade frontend image to version 1.2.3').
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.update_deployment_image(
                name=name,
                namespace=namespace,
                container_name=container_name,
                new_image=new_image,
            )
        )

    @tool
    def rollback_kubernetes_deployment(
        name: str,
        namespace: str,
        revision: int | None = None,
    ) -> dict[str, Any]:
        """Rollback a Kubernetes deployment to a previous revision.

        Use this when a rolling update fails, when pods crash after a new image update,
        or when the user explicitly requests to undo/rollback to a previous deployment
        version (e.g., 'rollback deployment frontend', 'undo last deployment for backend',
        or 'rollback frontend to revision 2').
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.rollback_deployment(
                name=name,
                namespace=namespace,
                revision=revision,
            )
        )

    @tool
    def pause_kubernetes_deployment(
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Pause a Kubernetes deployment to suspend its rollout controller.

        Use this when the user asks to pause, suspend, or freeze a deployment
        (e.g. 'pause deployment api in team-a').

        While paused, any spec changes (like image updates) are staged but
        NOT applied. The deployment resumes all staged changes at once when
        resume_kubernetes_deployment is called.

        Args:
            name:      Deployment name (e.g. 'backend').
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.pause_deployment(
                name=name,
                namespace=namespace,
            )
        )

    @tool
    def resume_kubernetes_deployment(
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Resume a paused Kubernetes deployment to apply its pending rollout.

        Use this when the user asks to resume, unfreeze, or unpause a deployment
        (e.g. 'resume deployment api in team-a').

        All spec changes accumulated while the deployment was paused are
        applied immediately as a single rolling update.

        Args:
            name:      Deployment name (e.g. 'backend').
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.resume_deployment(
                name=name,
                namespace=namespace,
            )
        )

    @tool
    def verify_kubernetes_service_selector(
        service_name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Verify that a Kubernetes Service's selector matches at least one live pod.

        USE THIS when:
        - The user reports that a service is unreachable or traffic is dropped
        - You suspect a labels mismatch between the Service selector and pod labels
        - You want to confirm how many Running pods are bound to a service

        Returns the selector, the list of matched pods, and an explicit
        LABELS MISMATCH alert if no pod matches the service selector.

        Args:
            service_name: Kubernetes Service name (e.g. 'backend', 'frontend').
            namespace:    Kubernetes namespace (must be in the allowed list).
        """
        return _call_deployment_service(
            lambda: deployment_manager_service.verify_service_selector(
                service_name=service_name,
                namespace=namespace,
            )
        )

    tools = [
        list_kubernetes_deployments,
        get_kubernetes_deployment,
        get_kubernetes_deployment_status,
        get_kubernetes_deployment_history,
        create_kubernetes_deployment,
        delete_kubernetes_deployment,
        scale_kubernetes_deployment,
        restart_kubernetes_deployment,
        update_kubernetes_deployment_image,
        rollback_kubernetes_deployment,
        pause_kubernetes_deployment,
        resume_kubernetes_deployment,
        verify_kubernetes_service_selector,
    ]
    for deployment_tool in tools:
        deployment_tool.handle_tool_error = _format_deployment_tool_error
        deployment_tool.handle_validation_error = INVALID_DEPLOYMENT_TOOL_INPUT_MESSAGE
    return tools
