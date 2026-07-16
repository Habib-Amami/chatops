"""Minimal ChatOps agent backed by LangChain and LangGraph."""

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from app.agent.prompts import CHATOPS_SYSTEM_PROMPT
from app.agent.tools.aws import create_ec2_tools, create_s3_tools
from app.agent.tools.kubernetes import create_pod_tools
from app.agent.tools.kubernetes.deployment_manager_tools import (
    create_deployment_manager_tools,
)
from app.platforms.aws.services import EC2Service, S3Service
from app.platforms.kubernetes.services import PodService
from app.platforms.kubernetes.services.deployment_manager_service import (
    DeploymentManagerService,
)


def create_chatops_agent(
    model: BaseChatModel,
    pod_service: PodService,
    deployment_manager_service: DeploymentManagerService,
    ec2_service: EC2Service,
    s3_service: S3Service | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Create a provider-neutral agent with Kubernetes, deployment, S3 and EC2 tools."""
    tools = list(create_pod_tools(pod_service))
    if s3_service is not None:
        tools.extend(create_s3_tools(s3_service))
    tools.extend(create_deployment_manager_tools(deployment_manager_service))
    tools.extend(create_ec2_tools(ec2_service))

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=CHATOPS_SYSTEM_PROMPT,
        name="chatops-agent",
    )
