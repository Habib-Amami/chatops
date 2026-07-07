"""Kubernetes API client creation for Minikube and in-cluster execution."""

from kubernetes import client as kubernetes_client
from kubernetes import config as kubernetes_config

from app.core import Settings


class KubernetesClientFactory:
    """Create and reuse Kubernetes API clients for the configured cluster."""

    def __init__(
        self,
        settings: Settings,
        api_client: kubernetes_client.ApiClient | None = None,
    ) -> None:
        self._settings = settings
        self._api_client = api_client
        self._core_v1_api: kubernetes_client.CoreV1Api | None = None
        self._apps_v1_api: kubernetes_client.AppsV1Api | None = None

    def get_api_client(self) -> kubernetes_client.ApiClient:
        """Return the shared low-level API client."""
        if self._api_client is not None:
            return self._api_client

        if self._settings.kubernetes_in_cluster:
            kubernetes_config.load_incluster_config()
            self._api_client = kubernetes_client.ApiClient()
        else:
            self._api_client = kubernetes_config.new_client_from_config(
                config_file=str(self._settings.kubeconfig),
                context=self._settings.kubernetes_context,
            )

        return self._api_client

    def get_core_v1_api(self) -> kubernetes_client.CoreV1Api:
        """Return a client for Pods, Services, Namespaces, and Events."""
        if self._core_v1_api is None:
            self._core_v1_api = kubernetes_client.CoreV1Api(self.get_api_client())
        return self._core_v1_api

    def get_apps_v1_api(self) -> kubernetes_client.AppsV1Api:
        """Return a client for Deployments, StatefulSets, and DaemonSets."""
        if self._apps_v1_api is None:
            self._apps_v1_api = kubernetes_client.AppsV1Api(self.get_api_client())
        return self._apps_v1_api
