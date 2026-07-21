"""Safe public container-registry image resolution and verification."""

from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from app.platforms.kubernetes.errors import ContainerRegistryError

_DOCKER_HUB_ALIASES = {
    "docker hub",
    "docker.io",
    "dockerhub",
    "index.docker.io",
    "registry-1.docker.io",
}
_REGISTRY_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[1-9][0-9]{0,4})?$"
)
_REPOSITORY_COMPONENT_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_TAG_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_AUTH_PARAMETER_PATTERN = re.compile(r'(\w+)="([^"]*)"')
_MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
_MAX_TOKEN_RESPONSE_BYTES = 64 * 1024


@dataclass(frozen=True)
class ContainerImageReference:
    """One normalized tagged image reference."""

    registry: str
    repository: str
    tag: str

    @property
    def pull_reference(self) -> str:
        """Return the fully qualified reference passed to Kubernetes."""
        return f"{self.registry}/{self.repository}:{self.tag}"


class ContainerRegistryClient:
    """Resolve and verify anonymous images on explicitly trusted registries."""

    def __init__(
        self,
        allowed_registries: list[str],
        default_registry: str = "docker.io",
        timeout_seconds: float = 5.0,
    ) -> None:
        self._allowed_registries = frozenset(
            self._normalize_registry(registry) for registry in allowed_registries
        )
        self._default_registry = self._normalize_registry(default_registry)
        self._timeout_seconds = timeout_seconds
        if self._default_registry not in self._allowed_registries:
            raise ContainerRegistryError(
                "The default container registry must be included in the allowed registries"
            )

    def resolve(
        self,
        image: str,
        registry: str | None = None,
    ) -> ContainerImageReference:
        """Normalize a repository and optional registry into a pull reference."""
        raw_image = image.strip()
        if not raw_image or any(character.isspace() for character in raw_image):
            raise ContainerRegistryError(
                "The container image cannot be empty or spaced"
            )
        if "://" in raw_image or "@" in raw_image:
            raise ContainerRegistryError(
                "Use an image in repository[:tag] form; URL schemes and digests "
                "are not supported yet"
            )

        image_registry, repository_and_tag = self._extract_embedded_registry(raw_image)
        requested_registry = (
            self._normalize_registry(registry)
            if registry is not None
            else image_registry or self._default_registry
        )
        if image_registry is not None and image_registry != requested_registry:
            raise ContainerRegistryError(
                f"Image registry {image_registry!r} conflicts with requested registry "
                f"{requested_registry!r}"
            )
        if requested_registry not in self._allowed_registries:
            allowed = ", ".join(sorted(self._allowed_registries))
            raise PermissionError(
                f"Container registry {requested_registry!r} is not allowed; "
                f"allowed registries: {allowed}"
            )

        repository, tag = self._split_repository_and_tag(repository_and_tag)
        if requested_registry == "docker.io" and "/" not in repository:
            repository = f"library/{repository}"
        self._validate_repository(repository)
        if not _TAG_PATTERN.fullmatch(tag):
            raise ContainerRegistryError(f"Container image tag {tag!r} is invalid")

        return ContainerImageReference(
            registry=requested_registry,
            repository=repository,
            tag=tag,
        )

    def verify_exists(self, image: ContainerImageReference) -> None:
        """Verify that an anonymously pullable image manifest exists."""
        manifest_url = self._manifest_url(image)
        status, headers, _ = self._request(
            "HEAD",
            manifest_url,
            headers={"Accept": _MANIFEST_ACCEPT},
        )
        if status == 401:
            token = self._request_bearer_token(image, headers)
            status, _, _ = self._request(
                "HEAD",
                manifest_url,
                headers={
                    "Accept": _MANIFEST_ACCEPT,
                    "Authorization": f"Bearer {token}",
                },
            )

        if status == 200:
            return
        if status == 404:
            raise ContainerRegistryError(
                f"Container image {image.pull_reference!r} was not found"
            )
        if status in {401, 403}:
            raise ContainerRegistryError(
                f"Container image {image.pull_reference!r} is private or cannot be "
                "verified anonymously"
            )
        if status == 429:
            raise ContainerRegistryError(
                f"Registry {image.registry!r} rate-limited the image check; try again later"
            )
        raise ContainerRegistryError(
            f"Registry {image.registry!r} returned HTTP {status} while verifying "
            f"{image.pull_reference!r}"
        )

    def _request_bearer_token(
        self,
        image: ContainerImageReference,
        headers: dict[str, str],
    ) -> str:
        challenge = self._get_header(headers, "WWW-Authenticate")
        if challenge is None or not challenge.lower().startswith("bearer "):
            raise ContainerRegistryError(
                f"Registry {image.registry!r} requires unsupported authentication"
            )

        parameters = dict(_AUTH_PARAMETER_PATTERN.findall(challenge[7:]))
        realm = parameters.get("realm")
        if realm is None:
            raise ContainerRegistryError(
                f"Registry {image.registry!r} returned an invalid authentication challenge"
            )
        self._validate_token_realm(image.registry, realm)

        parsed_realm = urlsplit(realm)
        query = list(parse_qsl(parsed_realm.query, keep_blank_values=True))
        if service := parameters.get("service"):
            query.append(("service", service))
        query.append(
            ("scope", parameters.get("scope", f"repository:{image.repository}:pull"))
        )
        token_url = parsed_realm._replace(query=urlencode(query, doseq=True)).geturl()
        status, _, body = self._request("GET", token_url)
        if status != 200:
            raise ContainerRegistryError(
                f"Registry token service returned HTTP {status} for "
                f"{image.pull_reference!r}"
            )
        try:
            token_data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ContainerRegistryError(
                "Registry token service returned an invalid response"
            ) from error
        token = token_data.get("token") or token_data.get("access_token")
        if not isinstance(token, str) or not token:
            raise ContainerRegistryError(
                "Registry token service did not return a bearer token"
            )
        return token

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        request_headers = {"User-Agent": "chatops-backend/0.1"}
        request_headers.update(headers or {})
        request = Request(url, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read(_MAX_TOKEN_RESPONSE_BYTES + 1)
                if len(body) > _MAX_TOKEN_RESPONSE_BYTES:
                    raise ContainerRegistryError(
                        "Registry response exceeded the verification size limit"
                    )
                return response.status, dict(response.headers.items()), body
        except HTTPError as error:
            body = error.read(_MAX_TOKEN_RESPONSE_BYTES + 1)
            return error.code, dict(error.headers.items()), body
        except (TimeoutError, URLError) as error:
            raise ContainerRegistryError(
                "The container registry could not be reached for image verification"
            ) from error

    @staticmethod
    def _extract_embedded_registry(image: str) -> tuple[str | None, str]:
        first_component, separator, remainder = image.partition("/")
        if separator and (
            "." in first_component
            or ":" in first_component
            or first_component == "localhost"
        ):
            return (
                ContainerRegistryClient._normalize_registry(first_component),
                remainder,
            )
        return None, image

    @staticmethod
    def _split_repository_and_tag(image: str) -> tuple[str, str]:
        last_component = image.rsplit("/", 1)[-1]
        if ":" not in last_component:
            return image, "latest"
        repository, tag = image.rsplit(":", 1)
        return repository, tag

    @staticmethod
    def _validate_repository(repository: str) -> None:
        if len(repository) >= 256 or any(
            not _REPOSITORY_COMPONENT_PATTERN.fullmatch(component)
            for component in repository.split("/")
        ):
            raise ContainerRegistryError(
                f"Container image repository {repository!r} is invalid"
            )

    @staticmethod
    def _normalize_registry(registry: str) -> str:
        normalized = registry.strip().lower().rstrip("/")
        if normalized in _DOCKER_HUB_ALIASES:
            return "docker.io"
        if "://" in normalized or "/" in normalized:
            raise ContainerRegistryError(
                "Specify a registry hostname without a URL scheme or path"
            )
        if not _REGISTRY_PATTERN.fullmatch(normalized):
            raise ContainerRegistryError(f"Container registry {registry!r} is invalid")
        port = normalized.rsplit(":", 1)[-1] if ":" in normalized else None
        if port is not None and int(port) > 65535:
            raise ContainerRegistryError(f"Container registry {registry!r} is invalid")
        return normalized

    @staticmethod
    def _validate_token_realm(registry: str, realm: str) -> None:
        parsed = urlsplit(realm)
        if parsed.scheme != "https" or parsed.hostname is None:
            raise ContainerRegistryError(
                "Registry authentication must use a valid HTTPS token service"
            )
        allowed_auth_hosts = (
            {"auth.docker.io"}
            if registry == "docker.io"
            else {registry.split(":", 1)[0]}
        )
        if parsed.hostname not in allowed_auth_hosts:
            raise ContainerRegistryError(
                "Registry authentication redirected to an untrusted token service"
            )

    @staticmethod
    def _manifest_url(image: ContainerImageReference) -> str:
        registry_host = (
            "registry-1.docker.io" if image.registry == "docker.io" else image.registry
        )
        repository = quote(image.repository, safe="/")
        tag = quote(image.tag, safe="")
        return f"https://{registry_host}/v2/{repository}/manifests/{tag}"

    @staticmethod
    def _get_header(headers: dict[str, str], name: str) -> str | None:
        expected = name.lower()
        return next(
            (value for key, value in headers.items() if key.lower() == expected),
            None,
        )
