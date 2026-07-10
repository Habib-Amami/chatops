"""Shared Kubernetes safety helpers."""

from collections.abc import Collection


def validate_kubernetes_namespace(
    namespace: str,
    allowed_namespaces: Collection[str],
) -> None:
    """Reject namespaces outside the configured ChatOps safety boundary."""
    if namespace not in allowed_namespaces:
        raise PermissionError(f"Namespace {namespace!r} is not allowed")
