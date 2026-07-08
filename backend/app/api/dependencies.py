"""Dependency wiring for API-facing application services."""

from functools import lru_cache

from app.agent import AgentService, create_chatops_agent
from app.agent.models import ChatModelFactory
from app.core import get_settings
from app.platforms.kubernetes import KubernetesClientFactory
from app.platforms.kubernetes.services import PodService


@lru_cache
def get_agent_service() -> AgentService:
    """Build and reuse the configured ChatOps service graph."""
    settings = get_settings()
    kubernetes_clients = KubernetesClientFactory(settings)
    pod_service = PodService(settings, kubernetes_clients)
    model = ChatModelFactory(settings).get_model()
    agent = create_chatops_agent(model, pod_service)
    return AgentService(agent)
