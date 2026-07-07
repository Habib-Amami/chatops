"""Boto3 client creation for LocalStack and AWS."""

from typing import Any

from boto3.session import Session
from botocore.client import BaseClient

from app.core import Settings


class AWSClientFactory:
    """Create and reuse Boto3 service clients for the configured AWS target."""

    def __init__(self, settings: Settings, session: Session | None = None) -> None:
        self._settings = settings
        self._session = session or Session()
        self._clients: dict[str, BaseClient] = {}

    def get_client(self, service_name: str) -> BaseClient:
        """Return a cached client configured for LocalStack or real AWS."""
        if service_name in self._clients:
            return self._clients[service_name]

        options: dict[str, Any] = {"region_name": self._settings.aws_region}

        if self._settings.aws_target == "localstack":
            options.update(
                endpoint_url=self._settings.aws_endpoint_url,
                aws_access_key_id=self._settings.aws_access_key_id.get_secret_value(),
                aws_secret_access_key=(
                    self._settings.aws_secret_access_key.get_secret_value()
                ),
            )

        aws_client = self._session.client(service_name, **options)
        self._clients[service_name] = aws_client
        return aws_client
