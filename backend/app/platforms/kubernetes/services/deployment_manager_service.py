"""Active Kubernetes Deployment management and orchestration."""

import datetime
from typing import Any, cast

from kubernetes import client as kubernetes_client

from app.core import Settings
from app.platforms.kubernetes import (
    KubernetesClientFactory,
    KubernetesOperationError,
    KubernetesResourceNotFoundError,
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

    # ------------------------------------------------------------------
    # Read / Inspection Methods
    # ------------------------------------------------------------------

    def list_deployments(self, namespace: str) -> list[dict[str, Any]]:
        """List all Deployments in an allowed namespace.

        Returns a condensed list of each deployment's name, namespace,
        desired/ready/available replica counts, and current conditions.

        Args:
            namespace: Kubernetes namespace (must be in the allowed list).

        Raises:
            PermissionError: If *namespace* is not in the allowed list.
            KubernetesOperationError: If the API call fails.
        """
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        raw_response = cast(
            kubernetes_client.V1DeploymentList,
            execute_kubernetes_api_call(
                operation="list Deployments",
                resource=f"namespace {namespace!r}",
                call=lambda: self._apps_v1_api.list_namespaced_deployment(
                    namespace=namespace
                ),
            ),
        )

        result: list[dict[str, Any]] = []
        for dep in raw_response.items or []:
            meta = dep.metadata
            spec = dep.spec
            status = dep.status
            if meta is None:
                continue
            result.append(
                {
                    "name": meta.name,
                    "namespace": meta.namespace or namespace,
                    "labels": meta.labels or {},
                    "desired_replicas": spec.replicas if spec else None,
                    "ready_replicas": status.ready_replicas if status else None,
                    "available_replicas": status.available_replicas if status else None,
                    "updated_replicas": status.updated_replicas if status else None,
                    "paused": bool(spec.paused) if spec else False,
                    "conditions": [
                        {
                            "type": c.type,
                            "status": c.status,
                            "reason": c.reason,
                            "message": c.message,
                        }
                        for c in (status.conditions or [])
                        if status
                    ],
                }
            )
        return result

    def get_deployment(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Get detailed information for a single named Deployment.

        Returns a structured dictionary including metadata, replica counts,
        container image(s), and current rollout conditions.

        Args:
            name:      Deployment name (e.g. 'backend').
            namespace: Kubernetes namespace (must be in the allowed list).

        Raises:
            PermissionError: If *namespace* is not in the allowed list.
            KubernetesResourceNotFoundError: If the Deployment does not exist.
            KubernetesOperationError: If the API call fails.
        """
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        raw = cast(
            kubernetes_client.V1Deployment,
            execute_kubernetes_api_call(
                operation="read Deployment",
                resource=f"{namespace}/{name}",
                call=lambda: self._apps_v1_api.read_namespaced_deployment(
                    name=name,
                    namespace=namespace,
                ),
            ),
        )
        if raw is None:
            raise KubernetesResourceNotFoundError(
                f"Deployment {namespace}/{name} was not found"
            )

        meta = raw.metadata
        spec = raw.spec
        status = raw.status
        containers = []
        if spec and spec.template and spec.template.spec:
            for c in spec.template.spec.containers or []:
                containers.append(
                    {
                        "name": c.name,
                        "image": c.image,
                        "ports": [
                            p.container_port for p in (c.ports or [])
                        ],
                    }
                )

        return {
            "name": meta.name if meta else name,
            "namespace": (meta.namespace if meta else None) or namespace,
            "labels": meta.labels if meta else {},
            "annotations": meta.annotations if meta else {},
            "creation_timestamp": (
                meta.creation_timestamp.isoformat()
                if meta and meta.creation_timestamp
                else None
            ),
            "desired_replicas": spec.replicas if spec else None,
            "ready_replicas": status.ready_replicas if status else None,
            "available_replicas": status.available_replicas if status else None,
            "updated_replicas": status.updated_replicas if status else None,
            "paused": bool(spec.paused) if spec else False,
            "strategy": (
                spec.strategy.type if spec and spec.strategy else None
            ),
            "containers": containers,
            "conditions": [
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                    "last_update": (
                        c.last_update_time.isoformat()
                        if c.last_update_time
                        else None
                    ),
                }
                for c in (status.conditions or [])
                if status
            ],
        }

    def get_deployment_status(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Get a focused rollout health snapshot for a single Deployment.

        Returns replica counts, readiness, and rollout conditions without
        returning the full Deployment spec. Useful for monitoring whether
        a rollout has completed or is stalled.

        Args:
            name:      Deployment name.
            namespace: Kubernetes namespace (must be in the allowed list).

        Raises:
            PermissionError: If *namespace* is not in the allowed list.
            KubernetesResourceNotFoundError: If the Deployment does not exist.
            KubernetesOperationError: If the API call fails.
        """
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        raw = cast(
            kubernetes_client.V1Deployment,
            execute_kubernetes_api_call(
                operation="read Deployment status",
                resource=f"{namespace}/{name}",
                call=lambda: self._apps_v1_api.read_namespaced_deployment_status(
                    name=name,
                    namespace=namespace,
                ),
            ),
        )
        if raw is None:
            raise KubernetesResourceNotFoundError(
                f"Deployment {namespace}/{name} was not found"
            )

        spec = raw.spec
        status = raw.status
        desired = spec.replicas if spec else None
        ready = status.ready_replicas if status else None
        available = status.available_replicas if status else None
        updated = status.updated_replicas if status else None

        # Determine a human-readable rollout state
        if desired is not None and ready == desired and updated == desired:
            rollout_state = "complete"
        elif updated is not None and desired is not None and updated < desired:
            rollout_state = "in_progress"
        elif ready is not None and desired is not None and ready < desired:
            rollout_state = "degraded"
        else:
            rollout_state = "unknown"

        return {
            "name": name,
            "namespace": namespace,
            "rollout_state": rollout_state,
            "desired_replicas": desired,
            "ready_replicas": ready,
            "available_replicas": available,
            "updated_replicas": updated,
            "paused": bool(spec.paused) if spec else False,
            "conditions": [
                {
                    "type": c.type,
                    "status": c.status,
                    "reason": c.reason,
                    "message": c.message,
                }
                for c in (status.conditions or [])
                if status
            ],
        }

    def get_deployment_history(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Get the rollout revision history for a single Deployment.

        Queries all ReplicaSets owned by the Deployment and returns them
        sorted by revision number (oldest first). Each entry includes the
        revision number and the container image(s) that were deployed.

        Args:
            name:      Deployment name.
            namespace: Kubernetes namespace (must be in the allowed list).

        Raises:
            PermissionError: If *namespace* is not in the allowed list.
            KubernetesOperationError: If the Deployment or ReplicaSets cannot
                be retrieved.
        """
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        # Confirm the deployment exists first
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

        history: list[dict[str, Any]] = []
        for rs in replica_sets.items or []:
            meta = rs.metadata
            if meta is None or not meta.owner_references:
                continue
            if not any(
                owner.kind == "Deployment" and owner.name == name
                for owner in meta.owner_references
            ):
                continue
            annotations = meta.annotations or {}
            revision_text = annotations.get("deployment.kubernetes.io/revision")
            if revision_text is None:
                continue
            try:
                revision = int(revision_text)
            except ValueError:
                continue

            images: list[str] = []
            if rs.spec and rs.spec.template and rs.spec.template.spec:
                images = [
                    c.image or "unknown"
                    for c in (rs.spec.template.spec.containers or [])
                ]

            history.append(
                {
                    "revision": revision,
                    "replica_set": meta.name,
                    "images": images,
                    "change_cause": annotations.get(
                        "kubernetes.io/change-cause", "<none>"
                    ),
                    "created_at": (
                        meta.creation_timestamp.isoformat()
                        if meta.creation_timestamp
                        else None
                    ),
                }
            )

        history.sort(key=lambda e: e["revision"])
        return {
            "deployment": name,
            "namespace": namespace,
            "total_revisions": len(history),
            "revisions": history,
        }

    # ------------------------------------------------------------------
    # Create / Delete Methods
    # ------------------------------------------------------------------

    def create_deployment(
        self,
        name: str,
        namespace: str,
        image: str,
        *,
        replicas: int = 1,
        container_name: str | None = None,
        port: int | None = None,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Deployment in an allowed namespace.

        Builds and submits a minimal, secure Deployment manifest.
        The Deployment uses a standard label selector based on the
        ``app`` label set to *name*. Only one container is created.

        Args:
            name:           Deployment name (also used as ``app`` label).
            namespace:      Kubernetes namespace (must be in the allowed list).
            image:          Full container image reference (e.g. ``nginx:1.27``).
            replicas:       Initial number of replicas (default 1).
            container_name: Container name inside the pod spec. Defaults to *name*.
            port:           Optional container port to expose in the spec.
            labels:         Additional labels merged onto the Deployment and
                            Pod template metadata.

        Raises:
            PermissionError: If *namespace* is not in the allowed list.
            KubernetesOperationError: If the API call fails (e.g. already exists).
        """
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        effective_container_name = container_name or name
        base_labels: dict[str, str] = {
            "app": name,
            "app.kubernetes.io/managed-by": "chatops",
        }
        if labels:
            base_labels.update(labels)

        container_ports: list[kubernetes_client.V1ContainerPort] = []
        if port is not None:
            container_ports.append(
                kubernetes_client.V1ContainerPort(container_port=port)
            )

        deployment = kubernetes_client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=kubernetes_client.V1ObjectMeta(
                name=name,
                namespace=namespace,
                labels=base_labels,
            ),
            spec=kubernetes_client.V1DeploymentSpec(
                replicas=replicas,
                selector=kubernetes_client.V1LabelSelector(
                    match_labels={"app": name}
                ),
                template=kubernetes_client.V1PodTemplateSpec(
                    metadata=kubernetes_client.V1ObjectMeta(labels={"app": name}),
                    spec=kubernetes_client.V1PodSpec(
                        automount_service_account_token=False,
                        containers=[
                            kubernetes_client.V1Container(
                                name=effective_container_name,
                                image=image,
                                image_pull_policy="IfNotPresent",
                                ports=container_ports or None,
                                resources=kubernetes_client.V1ResourceRequirements(
                                    requests={"cpu": "50m", "memory": "64Mi"},
                                    limits={"cpu": "250m", "memory": "256Mi"},
                                ),
                                security_context=kubernetes_client.V1SecurityContext(
                                    allow_privilege_escalation=False,
                                    capabilities=kubernetes_client.V1Capabilities(
                                        drop=["ALL"]
                                    ),
                                ),
                            )
                        ],
                        security_context=kubernetes_client.V1PodSecurityContext(
                            seccomp_profile=kubernetes_client.V1SeccompProfile(
                                type="RuntimeDefault"
                            )
                        ),
                    ),
                ),
                strategy=kubernetes_client.V1DeploymentStrategy(type="RollingUpdate"),
            ),
        )

        raw_response = execute_kubernetes_api_call(
            operation="create Deployment",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.create_namespaced_deployment(
                namespace=namespace,
                body=deployment,
            ),
        )
        return cast(
            dict[str, Any],
            self._api_client.sanitize_for_serialization(raw_response),
        )

    def delete_deployment(
        self,
        name: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Delete a Deployment from an allowed namespace.

        The Kubernetes garbage collector will cascade-delete the owned
        ReplicaSets and Pods automatically.

        Args:
            name:      Deployment name.
            namespace: Kubernetes namespace (must be in the allowed list).

        Raises:
            PermissionError: If *namespace* is not in the allowed list.
            KubernetesOperationError: If the API call fails.
        """
        validate_kubernetes_namespace(namespace, self._allowed_namespaces)

        execute_kubernetes_api_call(
            operation="delete Deployment",
            resource=f"{namespace}/{name}",
            call=lambda: self._apps_v1_api.delete_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=kubernetes_client.V1DeleteOptions(
                    propagation_policy="Foreground",
                    grace_period_seconds=0,
                ),
            ),
        )
        return {
            "status": "deleted",
            "deployment": name,
            "namespace": namespace,
            "message": (
                f"Deployment '{name}' in namespace '{namespace}' has been deleted. "
                "Kubernetes will cascade-delete its ReplicaSets and Pods."
            ),
        }

    # ------------------------------------------------------------------
    # Mutation Methods (Scale / Restart / Update / Rollback / Pause / Resume)
    # ------------------------------------------------------------------

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
