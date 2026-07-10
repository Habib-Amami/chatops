"""Active Kubernetes Deployment management and orchestration."""

import datetime
from typing import Any, cast
from kubernetes import client as kubernetes_client
from app.core import Settings
from app.platforms.kubernetes import KubernetesClientFactory

# Maximum tail lines a caller may request — prevents oversized LLM context payloads.
_MAX_TAIL_LINES = 200


class DeploymentManagerService:
    """Provide namespace-scoped, active Deployment management operations."""

    def __init__(
        self,
        settings: Settings,
        clients: KubernetesClientFactory,
    ) -> None:
        self._allowed_namespaces = frozenset(
            settings.kubernetes_allowed_namespaces
        )
        self._apps_v1_api = clients.get_apps_v1_api()
        self._core_v1_api = clients.get_core_v1_api()
        self._api_client = clients.get_api_client()

    def _validate_namespace(self, namespace: str) -> None:
        """Validate if the namespace is in the allowed list."""
        if namespace not in self._allowed_namespaces:
            raise PermissionError(f"Namespace {namespace!r} is not allowed")

    def scale_deployment(
        self,
        name: str,
        namespace: str,
        replicas: int,
    ) -> dict[str, Any]:
        """Scale a deployment to the specified number of replicas."""
        self._validate_namespace(namespace)

        body = {"spec": {"replicas": replicas}}
        try:
            raw_response = self._apps_v1_api.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body=body,
            )
            return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))
        except kubernetes_client.exceptions.ApiException as e:
            return {"error": f"Failed to scale deployment '{name}': {e.reason} ({e.status})"}

    def restart_deployment(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Trigger a rolling restart of a deployment."""
        self._validate_namespace(namespace)

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now
                        }
                    }
                }
            }
        }
        try:
            raw_response = self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            )
            return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))
        except kubernetes_client.exceptions.ApiException as e:
            return {"error": f"Failed to restart deployment '{name}': {e.reason} ({e.status})"}

    def update_deployment_image(
        self,
        name: str,
        namespace: str,
        container_name: str,
        new_image: str,
    ) -> dict[str, Any]:
        """Update the image of a specific container in a deployment."""
        self._validate_namespace(namespace)

        body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": container_name,
                                "image": new_image,
                            }
                        ]
                    }
                }
            }
        }
        try:
            raw_response = self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            )
            return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))
        except kubernetes_client.exceptions.ApiException as e:
            return {"error": f"Failed to update image of deployment '{name}': {e.reason} ({e.status})"}

    def rollback_deployment(
        self,
        name: str,
        namespace: str,
        revision: int | None = None,
    ) -> dict[str, Any]:
        """Rollback a deployment to a previous revision."""
        self._validate_namespace(namespace)

        try:
            # Retrieve the deployment to ensure it exists
            self._apps_v1_api.read_namespaced_deployment(name=name, namespace=namespace)

            # Retrieve all replica sets in the namespace
            rs_list = self._apps_v1_api.list_namespaced_replica_set(namespace=namespace)
            
            # Find ReplicaSets owned by this deployment
            owned_rs = []
            for rs in rs_list.items or []:
                if rs.metadata and rs.metadata.owner_references:
                    for ref in rs.metadata.owner_references:
                        if ref.kind == "Deployment" and ref.name == name:
                            owned_rs.append(rs)
                            break

            # Parse revisions
            rs_by_revision = {}
            for rs in owned_rs:
                if rs.metadata and rs.metadata.annotations:
                    rev_str = rs.metadata.annotations.get("deployment.kubernetes.io/revision")
                    if rev_str:
                        try:
                            rs_by_revision[int(rev_str)] = rs
                        except ValueError:
                            pass

            if not rs_by_revision:
                return {"error": f"No revisions found for deployment '{name}'."}

            sorted_revisions = sorted(rs_by_revision.keys())

            if revision is not None:
                target_rev = int(revision)
                if target_rev not in rs_by_revision:
                    return {
                        "error": f"Revision {target_rev} not found for deployment '{name}'. "
                                 f"Available revisions: {sorted_revisions}"
                    }
                target_rs = rs_by_revision[target_rev]
            else:
                if len(sorted_revisions) < 2:
                    return {
                        "error": f"No previous revision to rollback to for deployment '{name}'. "
                                 f"Current revision is the only revision available: {sorted_revisions}"
                    }
                # Second highest revision is the immediate previous one
                target_rev = sorted_revisions[-2]
                target_rs = rs_by_revision[target_rev]

            # Patch the deployment with the target ReplicaSet's pod template spec
            sanitized_template = self._api_client.sanitize_for_serialization(target_rs.spec.template)
            body = {
                "spec": {
                    "template": sanitized_template
                }
            }
            raw_response = self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            )
            return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))
        except kubernetes_client.exceptions.ApiException as e:
            return {"error": f"Failed to rollback deployment '{name}': {e.reason} ({e.status})"}
        except Exception as e:
            return {"error": f"Failed to rollback deployment '{name}': {str(e)}"}

    def get_pod_logs(
        self,
        pod_name: str,
        namespace: str,
        tail_lines: int = 50,
    ) -> str:
        """Return the tail logs of a running pod as a plain string.

        Args:
            pod_name:   Exact name of the pod (e.g. 'backend-6497b8ff45-6pvgm').
            namespace:  Kubernetes namespace the pod lives in.
            tail_lines: Number of log lines to fetch from the end.
                        Capped internally at _MAX_TAIL_LINES (200).

        Returns:
            A newline-separated string of recent log lines, or a message
            stating that no logs are available.

        Raises:
            PermissionError: If the namespace is not in the allowed list.
        """
        self._validate_namespace(namespace)

        # Cap tail_lines to avoid flooding the LLM context window.
        safe_tail = min(max(1, tail_lines), _MAX_TAIL_LINES)

        try:
            raw_logs: str | None = self._core_v1_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=safe_tail,
                timestamps=True,
            )
        except kubernetes_client.exceptions.ApiException as e:
            return f"Error retrieving logs for pod '{pod_name}' in namespace '{namespace}': {e.reason} ({e.status})"

        if not raw_logs or not raw_logs.strip():
            return f"No logs available for pod '{pod_name}' in namespace '{namespace}'."

        return raw_logs.strip()

    def delete_pod(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Delete/terminate a specific Kubernetes pod by name."""
        try:
            self._validate_namespace(namespace)
            raw_response = self._core_v1_api.delete_namespaced_pod(
                name=name,
                namespace=namespace,
            )
            return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))
        except PermissionError as e:
            return {"error": str(e)}
        except kubernetes_client.exceptions.ApiException as e:
            return {"error": f"Failed to delete pod '{name}': {e.reason} ({e.status})"}

    def get_pod_events(
        self,
        pod_name: str,
        namespace: str,
    ) -> str:
        """Fetch Kubernetes events for a specific pod (like kubectl describe pod).

        Essential for diagnosing pods that never started:
        ErrImageNeverPull, ImagePullBackOff, Pending, OOMKilled, etc.
        These pods have no container logs — events reveal the root cause.
        """
        try:
            self._validate_namespace(namespace)
            events = self._core_v1_api.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name}",
            )
            if not events.items:
                return f"No events found for pod '{pod_name}' in namespace '{namespace}'."
            lines = []
            for ev in events.items:
                reason = ev.reason or "Unknown"
                msg = ev.message or ""
                count = ev.count or 1
                ev_type = ev.type or "Normal"
                last_time = ev.last_timestamp or ev.event_time or "N/A"
                lines.append(f"[{ev_type}] {last_time} | {reason} (x{count}): {msg}")
            return "\n".join(lines)
        except PermissionError as e:
            return f"Error: {e}"
        except kubernetes_client.exceptions.ApiException as e:
            return f"Error fetching events for pod '{pod_name}': {e.reason} ({e.status})"

