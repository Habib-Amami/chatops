"""Agent tools for active Kubernetes Deployment orchestration."""

from typing import Any
from langchain.tools import BaseTool, tool
from app.platforms.kubernetes.services.deployment_manager_service import DeploymentManagerService


def create_deployment_manager_tools(
    deployment_manager_service: DeploymentManagerService,
) -> list[BaseTool]:
    """Create deployment orchestration tools bound to the management service."""

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
        return deployment_manager_service.scale_deployment(
            name=name,
            namespace=namespace,
            replicas=replicas,
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
        return deployment_manager_service.restart_deployment(
            name=name,
            namespace=namespace,
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
        return deployment_manager_service.update_deployment_image(
            name=name,
            namespace=namespace,
            container_name=container_name,
            new_image=new_image,
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
        return deployment_manager_service.rollback_deployment(
            name=name,
            namespace=namespace,
            revision=revision,
        )

    return [
        scale_kubernetes_deployment,
        restart_kubernetes_deployment,
        update_kubernetes_deployment_image,
        rollback_kubernetes_deployment,
    ]
