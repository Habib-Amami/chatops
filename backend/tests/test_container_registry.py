from unittest.mock import call, patch

import pytest

from app.platforms.kubernetes import ContainerRegistryError
from app.platforms.kubernetes.registry import (
    ContainerImageReference,
    ContainerRegistryClient,
)


def _registry_client() -> ContainerRegistryClient:
    return ContainerRegistryClient(
        allowed_registries=["docker.io", "ghcr.io", "quay.io"],
    )


def test_registry_client_defaults_to_docker_hub_library_image() -> None:
    image = _registry_client().resolve("nginx:alpine")

    assert image == ContainerImageReference(
        registry="docker.io",
        repository="library/nginx",
        tag="alpine",
    )
    assert image.pull_reference == "docker.io/library/nginx:alpine"


def test_registry_client_accepts_explicit_registry_and_default_tag() -> None:
    image = _registry_client().resolve("example/chatops", "ghcr.io")

    assert image.pull_reference == "ghcr.io/example/chatops:latest"


def test_registry_client_accepts_registry_in_image_reference() -> None:
    image = _registry_client().resolve("quay.io/example/chatops:v1")

    assert image.pull_reference == "quay.io/example/chatops:v1"


def test_registry_client_rejects_untrusted_registry() -> None:
    with pytest.raises(PermissionError, match="untrusted.example"):
        _registry_client().resolve("example/chatops:v1", "untrusted.example")


def test_registry_client_rejects_conflicting_registry_values() -> None:
    with pytest.raises(ContainerRegistryError, match="conflicts"):
        _registry_client().resolve("quay.io/example/chatops:v1", "ghcr.io")


def test_registry_client_verifies_docker_hub_image_with_bearer_token() -> None:
    client = _registry_client()
    image = client.resolve("nginx:alpine")
    challenge = (
        'Bearer realm="https://auth.docker.io/token",'
        'service="registry.docker.io",scope="repository:library/nginx:pull"'
    )

    with patch.object(
        client,
        "_request",
        side_effect=[
            (401, {"WWW-Authenticate": challenge}, b""),
            (200, {}, b'{"token":"registry-token"}'),
            (200, {}, b""),
        ],
    ) as request:
        client.verify_exists(image)

    manifest_url = "https://registry-1.docker.io/v2/library/nginx/manifests/alpine"
    assert request.call_args_list == [
        call(
            "HEAD",
            manifest_url,
            headers={"Accept": request.call_args_list[0].kwargs["headers"]["Accept"]},
        ),
        call(
            "GET",
            "https://auth.docker.io/token?service=registry.docker.io&scope="
            "repository%3Alibrary%2Fnginx%3Apull",
        ),
        call(
            "HEAD",
            manifest_url,
            headers={
                "Accept": request.call_args_list[2].kwargs["headers"]["Accept"],
                "Authorization": "Bearer registry-token",
            },
        ),
    ]


def test_registry_client_reports_missing_image() -> None:
    client = _registry_client()
    image = client.resolve("example/does-not-exist:v1")

    with (
        patch.object(client, "_request", return_value=(404, {}, b"")),
        pytest.raises(ContainerRegistryError, match="was not found"),
    ):
        client.verify_exists(image)


def test_registry_client_rejects_untrusted_token_service() -> None:
    client = _registry_client()
    image = client.resolve("nginx:alpine")
    challenge = 'Bearer realm="https://internal.example/token"'

    with (
        patch.object(
            client,
            "_request",
            return_value=(401, {"WWW-Authenticate": challenge}, b""),
        ),
        pytest.raises(ContainerRegistryError, match="untrusted token service"),
    ):
        client.verify_exists(image)
