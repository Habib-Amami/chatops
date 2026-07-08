"""Typed application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by the API, agent, and platform clients."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    model_provider: str | None = None
    model_name: str | None = None
    model_api_key: SecretStr | None = None

    aws_target: Literal["localstack", "aws"] = "localstack"
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_access_key_id: SecretStr = SecretStr("test")
    aws_secret_access_key: SecretStr = SecretStr("test")
    allow_real_aws: bool = False

    kubernetes_target: Literal["minikube", "kubernetes"] = "minikube"
    kubernetes_context: str = "minikube"
    kubernetes_in_cluster: bool = False
    kubeconfig: Path = Path.home() / ".kube" / "config"
    kubernetes_allowed_namespaces: list[str] = Field(
        default_factory=lambda: ["default", "chatops-demo"]
    )
    allow_real_kubernetes: bool = False

    @field_validator("kubeconfig")
    @classmethod
    def expand_kubeconfig_path(cls, value: Path) -> Path:
        """Expand a home-directory marker supplied through the environment."""
        return value.expanduser()

    @model_validator(mode="after")
    def validate_platform_safety(self) -> "Settings":
        """Reject ambiguous settings that could reach a real platform accidentally."""
        if self.aws_target == "localstack" and not self.aws_endpoint_url:
            raise ValueError("AWS_ENDPOINT_URL is required for LocalStack")
        if self.aws_target == "localstack" and (
            not self.aws_access_key_id.get_secret_value()
            or not self.aws_secret_access_key.get_secret_value()
        ):
            raise ValueError("LocalStack credentials must not be empty")
        if self.aws_target == "aws" and not self.allow_real_aws:
            raise ValueError("ALLOW_REAL_AWS must be true when AWS_TARGET=aws")

        if self.kubernetes_target == "minikube" and self.kubernetes_context != "minikube":
            raise ValueError("KUBERNETES_CONTEXT must be minikube for the Minikube target")
        if self.kubernetes_target == "kubernetes" and not self.allow_real_kubernetes:
            raise ValueError(
                "ALLOW_REAL_KUBERNETES must be true when "
                "KUBERNETES_TARGET=kubernetes"
            )
        if not self.kubernetes_allowed_namespaces:
            raise ValueError("At least one Kubernetes namespace must be allowed")

        return self


@lru_cache
def get_settings() -> Settings:
    """Return one settings instance for the application process."""
    return Settings()
