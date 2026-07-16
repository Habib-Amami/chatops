"""LangGraph server entrypoint for the ChatOps agent."""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from app.agent import create_chatops_agent
from app.agent.models import ChatModelFactory
from app.core import get_settings
from app.platforms.kubernetes import KubernetesClientFactory
from app.platforms.kubernetes.services import PodService


def build_graph(
    config: RunnableConfig | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Build the ChatOps graph for LangGraph server.

    The LangGraph server calls this factory from ``langgraph.json``. The
    optional config argument is accepted for compatibility with LangGraph's
    runtime graph factory interface.
    """
    del config

    settings = get_settings()
    kubernetes_clients = KubernetesClientFactory(settings)
    pod_service = PodService(settings, kubernetes_clients)
    model = ChatModelFactory(settings).get_model()
    return create_chatops_agent(model, pod_service)
