"""Active Kubernetes Deployment management and orchestration."""

import datetime
from typing import Any, cast

from kubernetes import client as kubernetes_client

from app.core import Settings
from app.platforms.kubernetes import (
    KubernetesClientFactory,
    KubernetesOperationError,
    execute_kubernetes_api_call,
    validate_kubernetes_namespace,
)


class DeploymentManagerService:
    """Provide namespace-scoped, active Deployment management operations."""

    def __init__(
        self,
        settings: Settings,
        clients: KubernetesClientFactory,
    ) -> None:
        self._allowed_namespaces = frozenset(settings.kubernetes_allowed_namespaces)
        self._apps_v1_api = clients.get_apps_v1_api()
        self._core_v1_api = clients.get_core_v1_api()
        self._api_client = clients.get_api_client()

    def scale_deployment(
        self,
        name: str,
        namespace: str,
        replicas: int,
    ) -> dict[str, Any]:
        """Scale a deployment to the specified number of replicas."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        body = {"spec": {"replicas": replicas}}
        raw_response = execute_kubernetes_api_call(
            operation="scale Deployment",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body=body,
            ),
        )
        return cast(
            dict[str, Any],
            self._api_client.sanitize_for_serialization(raw_response),
        )

    def restart_deployment(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Trigger a rolling restart of a deployment."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"kubectl.kubernetes.io/restartedAt": now}
                    }
                }
            }
        }
        raw_response = execute_kubernetes_api_call(
            operation="restart Deployment",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            ),
        )
        return cast(
            dict[str, Any],
            self._api_client.sanitize_for_serialization(raw_response),
        )

    def update_deployment_image(
        self,
        name: str,
        namespace: str,
        container_name: str,
        new_image: str,
    ) -> dict[str, Any]:
        """Update the image of a specific container in a deployment."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

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
        raw_response = execute_kubernetes_api_call(
            operation="update Deployment image",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            ),
        )
        return cast(
            dict[str, Any],
            self._api_client.sanitize_for_serialization(raw_response),
        )

    def rollback_deployment(
        self,
        name: str,
        namespace: str,
        revision: int | None = None,
    ) -> dict[str, Any]:
        """Rollback a deployment to a previous revision."""
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        execute_kubernetes_api_call(
            operation="read Deployment",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.read_namespaced_deployment(
                name=name,
                namespace=namespace,
            ),
        )
        replica_sets = cast(
            kubernetes_client.V1ReplicaSetList,
            execute_kubernetes_api_call(
                operation="list Deployment ReplicaSets",
                resource=f"namespace {namespace!r}",
                call=lambda: self._apps_v1_api.list_namespaced_replica_set(
                    namespace=namespace
                ),
            ),
        )

        owned_replica_sets = []
        for replica_set in replica_sets.items or []:
            metadata = replica_set.metadata
            if metadata is None or not metadata.owner_references:
                continue
            if any(
                owner.kind == "Deployment" and owner.name == name
                for owner in metadata.owner_references
            ):
                owned_replica_sets.append(replica_set)

        replica_sets_by_revision: dict[int, Any] = {}
        for replica_set in owned_replica_sets:
            annotations = replica_set.metadata.annotations
            revision_text = (
                annotations.get("deployment.kubernetes.io/revision")
                if annotations
                else None
            )
            if revision_text is None:
                continue
            try:
                replica_sets_by_revision[int(revision_text)] = replica_set
            except ValueError:
                continue

        if not replica_sets_by_revision:
            raise KubernetesOperationError(
                f"No revisions were found for Deployment {namespace}/{name}"
            )

        available_revisions = sorted(replica_sets_by_revision)
        if revision is not None:
            if revision not in replica_sets_by_revision:
                raise KubernetesOperationError(
                    f"Revision {revision} was not found for Deployment "
                    f"{namespace}/{name}; available revisions: {available_revisions}"
                )
            target_revision = revision
        else:
            if len(available_revisions) < 2:
                raise KubernetesOperationError(
                    f"No previous revision is available for Deployment "
                    f"{namespace}/{name}; current revision: {available_revisions[-1]}"
                )
            target_revision = available_revisions[-2]

        target_replica_set = replica_sets_by_revision[target_revision]
        target_template = getattr(
            getattr(target_replica_set, "spec", None),
            "template",
            None,
        )
        if target_template is None:
            raise KubernetesOperationError(
                f"Revision {target_revision} for Deployment {namespace}/{name} "
                "has no Pod template"
            )
        sanitized_template = self._api_client.sanitize_for_serialization(
            target_template
        )
        body = {"spec": {"template": sanitized_template}}
        raw_response = execute_kubernetes_api_call(
            operation=f"rollback Deployment to revision {target_revision}",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            ),
        )
        return cast(
            dict[str, Any],
            self._api_client.sanitize_for_serialization(raw_response),
        )

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
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        body = {"spec": {"paused": True}}
        execute_kubernetes_api_call(
            operation="pause Deployment",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            ),
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
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)
        body = {"spec": {"paused": False}}
        execute_kubernetes_api_call(
            operation="resume Deployment",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            ),
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
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        service = cast(
            kubernetes_client.V1Service,
            execute_kubernetes_api_call(
                operation="read Service",
                resource=f"{namespace}/{service_name}",
                call=lambda: self._core_v1_api.read_namespaced_service(
                    name=service_name,
                    namespace=namespace,
                ),
            ),
        )
        selector: dict[str, str] = (service.spec.selector or {}) if service.spec else {}

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

        label_selector = ",".join(f"{key}={value}" for key, value in selector.items())
        pods = cast(
            kubernetes_client.V1PodList,
            execute_kubernetes_api_call(
                operation="list Pods for Service selector",
                resource=f"{namespace}/{service_name}",
                call=lambda: self._core_v1_api.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                ),
            ),
        )

        running_pods = [
            pod.metadata.name
            for pod in (pods.items or [])
            if pod.status
            and pod.status.phase == "Running"
            and pod.metadata
            and pod.metadata.name
        ]
        all_matched_pods = [
            pod.metadata.name
            for pod in (pods.items or [])
            if pod.metadata and pod.metadata.name
        ]

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
