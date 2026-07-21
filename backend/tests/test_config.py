from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_default_to_local_platforms() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.aws_target == "localstack"
    assert settings.aws_endpoint_url == "http://localhost:4566"
    assert settings.aws_access_key_id.get_secret_value() == "test"
    assert settings.aws_secret_access_key.get_secret_value() == "test"
    assert settings.allow_real_aws is False
    assert settings.kubernetes_target == "minikube"
    assert settings.kubernetes_context == "minikube"
    assert settings.kubernetes_default_pod_registry == "docker.io"
    assert settings.kubernetes_allowed_pod_registries == [
        "docker.io",
        "ghcr.io",
        "quay.io",
    ]
    assert settings.kubernetes_registry_check_timeout_seconds == 5.0
    assert settings.kubernetes_pod_verification_timeout_seconds == 30.0
    assert settings.kubernetes_pod_verification_poll_seconds == 1.0
    assert settings.allow_real_kubernetes is False
    assert settings.model_timeout_seconds == 30.0
    assert settings.model_max_retries == 0
    assert settings.agent_timeout_seconds == 45.0


def test_settings_expand_kubeconfig_home_directory() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        kubeconfig="~/.kube/config",
    )

    assert settings.kubeconfig == Path.home() / ".kube" / "config"


def test_real_aws_requires_explicit_permission() -> None:
    with pytest.raises(ValidationError, match="ALLOW_REAL_AWS"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            aws_target="aws",
            aws_endpoint_url=None,
        )


def test_real_kubernetes_requires_explicit_permission() -> None:
    with pytest.raises(ValidationError, match="ALLOW_REAL_KUBERNETES"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            kubernetes_target="kubernetes",
            kubernetes_context="production",
        )


def test_default_pod_registry_must_be_allowed() -> None:
    with pytest.raises(ValidationError, match="KUBERNETES_DEFAULT_POD_REGISTRY"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            kubernetes_default_pod_registry="registry.example.com",
        )


def test_pod_verification_poll_cannot_exceed_timeout() -> None:
    with pytest.raises(
        ValidationError,
        match="KUBERNETES_POD_VERIFICATION_POLL_SECONDS",
    ):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            kubernetes_pod_verification_timeout_seconds=1,
            kubernetes_pod_verification_poll_seconds=2,
        )


def test_localstack_credentials_cannot_be_empty() -> None:
    with pytest.raises(ValidationError, match="LocalStack credentials"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            aws_access_key_id="",
        )


def test_secret_values_are_masked_in_settings_representation() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        aws_access_key_id="private-key",
    )

    assert "private-key" not in repr(settings)
