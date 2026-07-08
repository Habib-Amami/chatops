"""Minimal ChatOps agent backed by LangChain and LangGraph."""

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from app.agent.prompts import CHATOPS_SYSTEM_PROMPT
from app.agent.tools.kubernetes import create_pod_tools
from app.platforms.kubernetes.services import PodService


def create_chatops_agent(
    model: BaseChatModel,
    pod_service: PodService,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Create a provider-neutral, read-only agent with Kubernetes pod tools."""
    return create_agent(
        model=model,
        tools=create_pod_tools(pod_service),
        system_prompt=CHATOPS_SYSTEM_PROMPT,
        name="chatops-agent",
    )
