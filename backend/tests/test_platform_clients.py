from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core import Settings
from app.platforms.aws import AWSClientFactory
from app.platforms.kubernetes import KubernetesClientFactory


def test_aws_factory_configures_and_reuses_localstack_client() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    session = MagicMock()
    expected_client = MagicMock()
    session.client.return_value = expected_client
    factory = AWSClientFactory(settings, session=session)

    first_client = factory.get_client("lambda")
    second_client = factory.get_client("lambda")

    assert first_client is expected_client
    assert second_client is expected_client
    session.client.assert_called_once_with(
        "lambda",
        region_name="us-east-1",
        endpoint_url="http://localhost:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def test_aws_factory_uses_default_credential_chain_for_real_aws() -> None:
    settings = Settings(  
        _env_file=None, # pyright: ignore[reportCallIssue]
        aws_target="aws",
        aws_endpoint_url=None,
        allow_real_aws=True,
    )
    session = MagicMock()
    factory = AWSClientFactory(settings, session=session)

    factory.get_client("s3")

    session.client.assert_called_once_with("s3", region_name="us-east-1")


@patch("app.platforms.kubernetes.client.kubernetes_config.new_client_from_config")
def test_kubernetes_factory_loads_and_reuses_kubeconfig_client(
    new_client_from_config: MagicMock,
) -> None:
    expected_client = MagicMock()
    new_client_from_config.return_value = expected_client
    settings = Settings(
        _env_file=None, # pyright: ignore[reportCallIssue]
        kubeconfig=Path("/tmp/test-kubeconfig"),
    )
    factory = KubernetesClientFactory(settings)

    first_client = factory.get_api_client()
    second_client = factory.get_api_client()

    assert first_client is expected_client
    assert second_client is expected_client
    new_client_from_config.assert_called_once_with(
        config_file="/tmp/test-kubeconfig",
        context="minikube",
    )


@patch("app.platforms.kubernetes.client.kubernetes_client.ApiClient")
@patch("app.platforms.kubernetes.client.kubernetes_config.load_incluster_config")
def test_kubernetes_factory_supports_in_cluster_configuration(
    load_incluster_config: MagicMock,
    api_client_class: MagicMock,
) -> None:
    expected_client = MagicMock()
    api_client_class.return_value = expected_client
    settings = Settings(
        _env_file=None, # pyright: ignore[reportCallIssue]
        kubernetes_target="kubernetes",
        kubernetes_context="production",
        kubernetes_in_cluster=True,
        allow_real_kubernetes=True,
    )
    factory = KubernetesClientFactory(settings)

    result = factory.get_api_client()

    assert result is expected_client
    load_incluster_config.assert_called_once_with()
    api_client_class.assert_called_once_with()
