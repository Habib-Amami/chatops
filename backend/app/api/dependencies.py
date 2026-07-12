"""Dependency wiring for API-facing application services."""

from functools import lru_cache

from app.agent import AgentService, create_chatops_agent
from app.agent.models import ChatModelFactory
from app.core import get_settings
from app.platforms.aws import AWSClientFactory
from app.platforms.aws.services import S3Service
from app.platforms.kubernetes import KubernetesClientFactory
from app.platforms.kubernetes.services import PodService
from app.platforms.kubernetes.services.deployment_manager_service import DeploymentManagerService


@lru_cache
def get_agent_service() -> AgentService:
    """Build and reuse the configured ChatOps service graph."""
    settings = get_settings()

    # Kubernetes
    kubernetes_clients = KubernetesClientFactory(settings)
    pod_service = PodService(settings, kubernetes_clients)
    deployment_manager_service = DeploymentManagerService(
        settings,
        kubernetes_clients
    )

    # AWS / LocalStack
    aws_clients = AWSClientFactory(settings)
    s3_service = S3Service(settings, aws_clients)

    # Agent
    model = ChatModelFactory(settings).get_model()
    agent = create_chatops_agent(
        model,
        pod_service,
        s3_service,
        deployment_manager_service
    )

    return AgentService(agent)
