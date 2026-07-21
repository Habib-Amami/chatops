"""Domain errors raised by Kubernetes platform services."""


class KubernetesOperationError(RuntimeError):
    """A Kubernetes API operation failed without exposing SDK internals."""


class KubernetesResourceNotFoundError(KubernetesOperationError):
    """The requested Kubernetes resource does not exist."""


class KubernetesAccessDeniedError(KubernetesOperationError):
    """The Kubernetes API denied access to the requested resource."""


class KubernetesValidationError(KubernetesOperationError):
    """A Kubernetes resource name or operation parameter was invalid."""


class ContainerRegistryError(KubernetesOperationError):
    """A container image reference or public-registry verification failed."""
