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

    @tool
    def get_kubernetes_pod_logs(
        pod_name: str,
        namespace: str,
        tail_lines: int = 50,
    ) -> str:
        """Fetch the most recent log lines from a running Kubernetes pod.

        CRITICAL: Use EXACTLY the pod_name the user specifies or that
        list_kubernetes_pods returned. Never substitute a different pod name.

        NOTE: Pods in ErrImageNeverPull, ImagePullBackOff, or Pending state
        have NO container logs. Use get_kubernetes_pod_events for those instead.

        SELF-HEALING ORCHESTRATION LOOP (only when user asks to 'analyze and fix'):
        Step 1 — Call list_kubernetes_pods to confirm the pod exists and its status.
        Step 2 — If pod status is ErrImageNeverPull / ImagePullBackOff / Pending:
                 → call get_kubernetes_pod_events (not this tool) to find the cause.
        Step 3 — If pod is Running/CrashLoopBackOff: call this tool for logs.
        Step 4 — Identify root cause from logs:
            * 'CrashLoopBackOff' → restart with restart_kubernetes_deployment.
            * 'OOMKilled'        → report to user, suggest scaling replicas.
            * DB/connection err  → report the dependency issue, do NOT restart.
            * No obvious error   → show logs verbatim, ask user for guidance.
        Step 5 — Confirm every action taken and its outcome to the user.

        IMPORTANT: Never apply more than one fix at a time without reporting back first.

        Args:
            pod_name:   Exact pod name (e.g. 'backend-6497b8ff45-6pvgm').
            namespace:  Kubernetes namespace (must be in the allowed list).
            tail_lines: Number of log lines to retrieve (default 50, max 200).
        """
        return deployment_manager_service.get_pod_logs(
            pod_name=pod_name,
            namespace=namespace,
            tail_lines=tail_lines,
        )

    @tool
    def delete_kubernetes_pod(
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Delete/terminate a specific Kubernetes pod by name.

        Use this when the user explicitly requests to delete, terminate, destroy,
        kill, or remove a pod (e.g. 'delete pod backend-abc-123 in demo-app').
        Deleting a pod managed by a Deployment will cause Kubernetes to automatically
        replace it with a new pod.
        """
        return deployment_manager_service.delete_pod(
            name=name,
            namespace=namespace,
        )

    @tool
    def get_kubernetes_pod_events(
        pod_name: str,
        namespace: str,
    ) -> str:
        """Fetch Kubernetes events for a pod (equivalent to 'kubectl describe pod').

        USE THIS for pods that have NOT started (no container logs available):
        - ErrImageNeverPull  → image cannot be pulled (wrong tag, private registry)
        - ImagePullBackOff   → image pull is failing repeatedly
        - Pending            → pod is stuck waiting for resources/scheduling
        - OOMKilled          → pod was killed by kernel out-of-memory

        Events show the real error message (e.g. image not found, quota exceeded).
        Always call this BEFORE get_kubernetes_pod_logs for non-Running pods.

        Args:
            pod_name:  Exact pod name (e.g. 'backend-75bbccfb77-rzllv').
            namespace: Kubernetes namespace (must be in the allowed list).
        """
        return deployment_manager_service.get_pod_events(
            pod_name=pod_name,
            namespace=namespace,
        )

    return [
        scale_kubernetes_deployment,
        restart_kubernetes_deployment,
        update_kubernetes_deployment_image,
        rollback_kubernetes_deployment,
        get_kubernetes_pod_logs,
        delete_kubernetes_pod,
        get_kubernetes_pod_events,
    ]
