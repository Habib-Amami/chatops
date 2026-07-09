"""Active Kubernetes Deployment management and orchestration."""

import datetime
from typing import Any, cast
from kubernetes import client as kubernetes_client
from app.core import Settings
from app.platforms.kubernetes import KubernetesClientFactory


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
        raw_response = self._apps_v1_api.patch_namespaced_deployment_scale(
            name=name,
            namespace=namespace,
            body=body,
        )
        return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))

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
        raw_response = self._apps_v1_api.patch_namespaced_deployment(
            name=name,
            namespace=namespace,
            body=body,
        )
        return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))

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
        raw_response = self._apps_v1_api.patch_namespaced_deployment(
            name=name,
            namespace=namespace,
            body=body,
        )
        return cast(dict[str, Any], self._api_client.sanitize_for_serialization(raw_response))

    def rollback_deployment(
        self,
        name: str,
        namespace: str,
        revision: int | None = None,
    ) -> dict[str, Any]:
        """Rollback a deployment to a previous revision."""
        self._validate_namespace(namespace)

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
            raise ValueError(f"No revisions found for deployment {name}")

        sorted_revisions = sorted(rs_by_revision.keys())

        if revision is not None:
            target_rev = int(revision)
            if target_rev not in rs_by_revision:
                raise ValueError(
                    f"Revision {target_rev} not found for deployment {name}. "
                    f"Available revisions: {sorted_revisions}"
                )
            target_rs = rs_by_revision[target_rev]
        else:
            if len(sorted_revisions) < 2:
                raise ValueError(
                    f"No previous revision to rollback to for deployment {name}. "
                    f"Current revision is the only revision available: {sorted_revisions}"
                )
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
