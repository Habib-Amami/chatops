"""Shared Kubernetes safety helpers."""

import re
from collections.abc import Collection

from app.platforms.kubernetes.errors import KubernetesValidationError

_DNS_1123_SUBDOMAIN_PATTERN = re.compile(
    r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*$"
)


def validate_kubernetes_namespace(
    namespace: str,
    allowed_namespaces: Collection[str],
) -> None:
    """Ensure a namespace is inside the configured ChatOps safety boundary.

    Args:
        namespace: Exact Kubernetes namespace requested by the caller.
        allowed_namespaces: Namespaces the application is permitted to access.

    Raises:
        PermissionError: If the requested namespace is not allowed.
    """
    if namespace not in allowed_namespaces:
        raise PermissionError(f"Namespace {namespace!r} is not allowed")


def validate_kubernetes_pod_name(name: str) -> None:
    """Validate a Pod ``metadata.name`` using Kubernetes DNS-1123 rules.

    Args:
        name: Exact Pod name supplied by the caller.

    Raises:
        KubernetesValidationError: If the name exceeds 253 characters or does
            not use the lowercase DNS-1123 subdomain syntax required for Pods.
    """
    if len(name) > 253 or _DNS_1123_SUBDOMAIN_PATTERN.fullmatch(name) is None:
        raise KubernetesValidationError(
            f"Pod name {name!r} must be at most 253 characters, contain only "
            "lowercase letters, numbers, '-' or '.', and start and end with "
            "a letter or number"
        )
