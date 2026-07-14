import pytest

from app.platforms.kubernetes import validate_kubernetes_namespace


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
