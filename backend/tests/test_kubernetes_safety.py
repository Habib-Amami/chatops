import pytest

from app.platforms.kubernetes import (
    KubernetesValidationError,
    validate_kubernetes_namespace,
    validate_kubernetes_pod_name,
)


def test_validate_kubernetes_namespace_accepts_allowed_namespace() -> None:
    validate_kubernetes_namespace(
        "chatops-demo",
        {"default", "chatops-demo"},
    )


def test_validate_kubernetes_namespace_rejects_disallowed_namespace() -> None:
    with pytest.raises(PermissionError, match="kube-system"):
        validate_kubernetes_namespace(
            "kube-system",
            {"default", "chatops-demo"},
        )


@pytest.mark.parametrize(
    "name",
    [
        "manual-test",
        "api.v1",
        "a",
        "a" * 64,
        "a" * 253,
    ],
)
def test_validate_kubernetes_pod_name_accepts_dns_subdomains(name: str) -> None:
    validate_kubernetes_pod_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "Manual-Test",
        "-manual-test",
        "manual-test-",
        "manual_test",
        "a" * 254,
        "api..v1",
    ],
)
def test_validate_kubernetes_pod_name_rejects_invalid_names(name: str) -> None:
    with pytest.raises(KubernetesValidationError, match="Pod name"):
        validate_kubernetes_pod_name(name)
