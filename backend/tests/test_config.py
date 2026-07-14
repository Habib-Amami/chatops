from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_default_to_local_platforms() -> None:
    settings = Settings(_env_file=None) # pyright: ignore[reportCallIssue]

    assert settings.aws_target == "localstack"
    assert settings.aws_endpoint_url == "http://localhost:4566"
    assert settings.aws_access_key_id.get_secret_value() == "test"
    assert settings.aws_secret_access_key.get_secret_value() == "test"
    assert settings.allow_real_aws is False
    assert settings.kubernetes_target == "minikube"
    assert settings.kubernetes_context == "minikube"
    assert settings.allow_real_kubernetes is False
    assert settings.model_timeout_seconds == 30.0
    assert settings.model_max_retries == 0
    assert settings.agent_timeout_seconds == 45.0


def test_settings_expand_kubeconfig_home_directory() -> None:
    settings = Settings(  
        _env_file=None, # pyright: ignore[reportCallIssue]
        kubeconfig="~/.kube/config",
    )

    assert settings.kubeconfig == Path.home() / ".kube" / "config"


def test_real_aws_requires_explicit_permission() -> None:
    with pytest.raises(ValidationError, match="ALLOW_REAL_AWS"):
        Settings( 
            _env_file=None, # pyright: ignore[reportCallIssue]
            aws_target="aws",
            aws_endpoint_url=None,
        )


def test_real_kubernetes_requires_explicit_permission() -> None:
    with pytest.raises(ValidationError, match="ALLOW_REAL_KUBERNETES"):
        Settings(  
            _env_file=None, # pyright: ignore[reportCallIssue]
            kubernetes_target="kubernetes",
            kubernetes_context="production",
        )


def test_localstack_credentials_cannot_be_empty() -> None:
    with pytest.raises(ValidationError, match="LocalStack credentials"):
        Settings(
            _env_file=None, # pyright: ignore[reportCallIssue]
            aws_access_key_id="",
        )


def test_secret_values_are_masked_in_settings_representation() -> None:
    settings = Settings(
        _env_file=None, # pyright: ignore[reportCallIssue]
        aws_access_key_id="private-key",
    )

    assert "private-key" not in repr(settings)
