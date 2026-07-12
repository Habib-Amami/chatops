"""Minimal ChatOps agent backed by LangChain and LangGraph."""

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from app.agent.prompts import CHATOPS_SYSTEM_PROMPT
from app.agent.tools.aws import create_s3_tools
from app.agent.tools.kubernetes import create_pod_tools
from app.agent.tools.kubernetes.deployment_manager_tools import (
    create_deployment_manager_tools,
)

from app.platforms.aws.services import S3Service
from app.platforms.kubernetes.services import PodService
from app.platforms.kubernetes.services.deployment_manager_service import (
    DeploymentManagerService,
)


def create_chatops_agent(
    model: BaseChatModel,
    pod_service: PodService,
    s3_service: S3Service,
    deployment_manager_service: DeploymentManagerService,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Create a provider-neutral agent with Kubernetes, deployment and S3 tools."""

    tools = (
        create_pod_tools(pod_service)
        + create_s3_tools(s3_service)
        + create_deployment_manager_tools(deployment_manager_service)
    )

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=CHATOPS_SYSTEM_PROMPT,
        name="chatops-agent",
    )
