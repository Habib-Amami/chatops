from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_default_to_local_platforms() -> None:
    settings = Settings(_env_file=None)

    assert settings.aws_target == "localstack"
    assert settings.aws_endpoint_url == "http://localhost:4566"
    assert settings.aws_access_key_id.get_secret_value() == "test"
    assert settings.aws_secret_access_key.get_secret_value() == "test"
    assert settings.allow_real_aws is False
    assert settings.kubernetes_target == "minikube"
    assert settings.kubernetes_context == "minikube"
    assert settings.allow_real_kubernetes is False


def test_settings_expand_kubeconfig_home_directory() -> None:
    settings = Settings(_env_file=None, kubeconfig="~/.kube/config")

    assert settings.kubeconfig == Path.home() / ".kube" / "config"


def test_real_aws_requires_explicit_permission() -> None:
    with pytest.raises(ValidationError, match="ALLOW_REAL_AWS"):
        Settings(_env_file=None, aws_target="aws", aws_endpoint_url=None)


def test_real_kubernetes_requires_explicit_permission() -> None:
    with pytest.raises(ValidationError, match="ALLOW_REAL_KUBERNETES"):
        Settings(
            _env_file=None,
            kubernetes_target="kubernetes",
            kubernetes_context="production",
        )


def test_localstack_credentials_cannot_be_empty() -> None:
    with pytest.raises(ValidationError, match="LocalStack credentials"):
        Settings(_env_file=None, aws_access_key_id="")


def test_langsmith_tracing_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="LANGSMITH_API_KEY"):
        Settings(_env_file=None, langsmith_tracing=True)


def test_secret_values_are_masked_in_settings_representation() -> None:
    settings = Settings(_env_file=None, langsmith_api_key="private-key")

    assert "private-key" not in repr(settings)
