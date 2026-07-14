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

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    def pause_deployment(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Pause a deployment to suspend its rollout controller.

        While paused, any changes to the deployment spec (e.g. image updates)
        are accumulated but NOT applied until the deployment is resumed.
        Equivalent to: kubectl rollout pause deployment/<name>
        """
        try:
            self._validate_namespace(namespace)
            body = {"spec": {"paused": True}}
            raw_response = self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            )
            return {
                "status": "paused",
                "deployment": name,
                "namespace": namespace,
                "message": (
                    f"Deployment '{name}' in namespace '{namespace}' has been paused. "
                    "No new rollout will start until it is resumed."
                ),
            }
        except PermissionError as e:
            return {"status": "error", "reason": str(e)}
        except kubernetes_client.exceptions.ApiException as e:
            return {
                "status": "error",
                "reason": f"Failed to pause deployment '{name}': {e.reason} ({e.status})",
            }

    def resume_deployment(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Resume a paused deployment to trigger its pending rollout.

        Any spec changes accumulated while paused are applied immediately
        as a single rolling update.
        Equivalent to: kubectl rollout resume deployment/<name>
        """
        try:
            self._validate_namespace(namespace)
            body = {"spec": {"paused": False}}
            raw_response = self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            )
            return {
                "status": "resumed",
                "deployment": name,
                "namespace": namespace,
                "message": (
                    f"Deployment '{name}' in namespace '{namespace}' has been resumed. "
                    "A rolling update will now apply any accumulated changes."
                ),
            }
        except PermissionError as e:
            return {"status": "error", "reason": str(e)}
        except kubernetes_client.exceptions.ApiException as e:
            return {
                "status": "error",
                "reason": f"Failed to resume deployment '{name}': {e.reason} ({e.status})",
            }

    # ------------------------------------------------------------------
    # Advanced Diagnostic — Pod Status (no-log diagnosis)
    # ------------------------------------------------------------------

    def diagnose_pod_status(
        self,
        pod_name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Deeply inspect a pod's container statuses for advanced diagnosis.

        Reads the live pod status object and extracts container-level state
        details. Particularly useful when logs are unavailable (e.g. the
        container never started) because it surfaces the exact Kubernetes
        reason and message from the container status itself.

        Returns a structured dict that the LLM can interpret to decide the
        next remediation action.
        """
        try:
            self._validate_namespace(namespace)
            pod = self._core_v1_api.read_namespaced_pod_status(
                name=pod_name,
                namespace=namespace,
            )

            phase = pod.status.phase if pod.status else "Unknown"
            container_statuses = (pod.status.container_statuses or []) if pod.status else []

            if not container_statuses:
                return {
                    "status": "no_container_info",
                    "pod": pod_name,
                    "namespace": namespace,
                    "phase": phase,
                    "message": (
                        "No container status information is available yet. "
                        "The pod may still be in Pending/Scheduling phase."
                    ),
                }

            containers = []
            for cs in container_statuses:
                container_info: dict[str, Any] = {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": "unknown",
                }

                if cs.state:
                    if cs.state.running:
                        container_info["state"] = "Running"
                        container_info["started_at"] = str(cs.state.running.started_at)

                    elif cs.state.terminated:
                        t = cs.state.terminated
                        container_info["state"] = "Terminated"
                        container_info["exit_code"] = t.exit_code
                        container_info["reason"] = t.reason or "Unknown"
                        container_info["message"] = t.message or "No message provided."
                        container_info["finished_at"] = str(t.finished_at)

                    elif cs.state.waiting:
                        w = cs.state.waiting
                        container_info["state"] = "Waiting"
                        container_info["reason"] = w.reason or "Unknown"
                        container_info["message"] = w.message or (
                            "No additional message. Check pod events for more detail."
                        )

                containers.append(container_info)

            return {
                "status": "ok",
                "pod": pod_name,
                "namespace": namespace,
                "phase": phase,
                "containers": containers,
            }

        except PermissionError as e:
            return {"status": "error", "reason": str(e)}
        except kubernetes_client.exceptions.ApiException as e:
            return {
                "status": "error",
                "reason": (
                    f"Failed to read status for pod '{pod_name}': "
                    f"{e.reason} ({e.status})"
                ),
            }

    # ------------------------------------------------------------------
    # Network Mesh Diagnostic — Service Selector / Labels Mismatch
    # ------------------------------------------------------------------

    def verify_service_selector(
        self,
        service_name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Verify that a Kubernetes Service selector matches at least one live pod.

        A common misconfiguration is a Service whose label selector does not
        match any running pod (labels mismatch), meaning traffic is silently
        dropped. This method detects that scenario and surfaces an explicit
        warning for the LLM to report to the user.

        Returns:
            A structured dict with the selector used, matched pods, and an
            explicit alert if no pods are bound to the service.
        """
        try:
            self._validate_namespace(namespace)

            # Step 1 — fetch the Service and its selector
            svc = self._core_v1_api.read_namespaced_service(
                name=service_name,
                namespace=namespace,
            )
            selector: dict[str, str] = (svc.spec.selector or {}) if svc.spec else {}

            if not selector:
                return {
                    "status": "warning",
                    "service": service_name,
                    "namespace": namespace,
                    "selector": {},
                    "matched_pods": [],
                    "message": (
                        f"Service '{service_name}' has NO selector defined. "
                        "It cannot route traffic to any pod automatically. "
                        "This is intentional only for ExternalName or headless services."
                    ),
                }

            # Step 2 — list pods matching the selector
            label_selector_str = ",".join(f"{k}={v}" for k, v in selector.items())
            pods = self._core_v1_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector_str,
            )

            running_pods = [
                p.metadata.name
                for p in (pods.items or [])
                if p.status and p.status.phase == "Running"
                and p.metadata and p.metadata.name
            ]
            all_matched_pods = [
                p.metadata.name
                for p in (pods.items or [])
                if p.metadata and p.metadata.name
            ]

            # Step 3 — build result with explicit Labels Mismatch alert
            if not all_matched_pods:
                return {
                    "status": "labels_mismatch",
                    "service": service_name,
                    "namespace": namespace,
                    "selector": selector,
                    "matched_pods": [],
                    "running_pods": [],
                    "message": (
                        f"⚠️  LABELS MISMATCH DETECTED for Service '{service_name}'. "
                        f"Selector {selector} does not match any pod in namespace "
                        f"'{namespace}'. Traffic sent to this service will be dropped. "
                        "Verify that your pods carry the correct labels."
                    ),
                }

            return {
                "status": "ok",
                "service": service_name,
                "namespace": namespace,
                "selector": selector,
                "matched_pods": all_matched_pods,
                "running_pods": running_pods,
                "message": (
                    f"Service '{service_name}' selector {selector} matches "
                    f"{len(all_matched_pods)} pod(s), of which "
                    f"{len(running_pods)} are Running."
                ),
            }

        except PermissionError as e:
            return {"status": "error", "reason": str(e)}
        except kubernetes_client.exceptions.ApiException as e:
            return {
                "status": "error",
                "reason": (
                    f"Failed to verify selector for service '{service_name}': "
                    f"{e.reason} ({e.status})"
                ),
            }
