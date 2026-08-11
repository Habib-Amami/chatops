"""Minimal ChatOps agent backed by LangChain and LangGraph."""

from collections import Counter
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
)
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.agent.middleware import (
    ModelLimitErrorMiddleware,
    MutationAuditMiddleware,
    MutationAuditRecorder,
)
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

MUTATION_APPROVALS: dict[str, Any] = {
    "create_kubernetes_pod": {
        "allowed_decisions": ["approve", "reject"],
        "description": (
            "Review this standalone Pod creation carefully. It has no workload "
            "controller, so Kubernetes will not recreate it after deletion."
        ),
    },
    "delete_kubernetes_pod": {
        "allowed_decisions": ["approve", "reject"],
        "description": (
            "Review this Pod deletion carefully. A workload controller may "
            "recreate the Pod; an unmanaged Pod will not be recreated automatically."
        ),
    },
    "create_kubernetes_deployment": {
        "allowed_decisions": ["approve", "reject"],
        "description": (
            "Review this Deployment creation, including its namespace, image, "
            "replica count, container name, and optional port."
        ),
    },
    "delete_kubernetes_deployment": {
        "allowed_decisions": ["approve", "reject"],
        "description": (
            "Review this Deployment deletion carefully. Kubernetes will also "
            "remove its owned ReplicaSets and Pods."
        ),
    },
    "scale_kubernetes_deployment": {
        "allowed_decisions": ["approve", "reject"],
        "description": "Review the requested Deployment replica count.",
    },
    "restart_kubernetes_deployment": {
        "allowed_decisions": ["approve", "reject"],
        "description": "Review this rolling Deployment restart.",
    },
    "update_kubernetes_deployment_image": {
        "allowed_decisions": ["approve", "reject"],
        "description": "Review the Deployment container image change.",
    },
    "rollback_kubernetes_deployment": {
        "allowed_decisions": ["approve", "reject"],
        "description": "Review this Deployment rollback and revision.",
    },
    "pause_kubernetes_deployment": {
        "allowed_decisions": ["approve", "reject"],
        "description": "Review pausing this Deployment rollout.",
    },
    "resume_kubernetes_deployment": {
        "allowed_decisions": ["approve", "reject"],
        "description": "Review resuming this Deployment rollout.",
    },
}
MUTATING_TOOL_NAMES = frozenset(MUTATION_APPROVALS)


def create_chatops_tools(
    pod_service: PodService,
    deployment_manager_service: DeploymentManagerService,
    ec2_service: EC2Service,
    s3_service: S3Service,
) -> list[BaseTool]:
    """Build the complete tool registry used by the ChatOps agent.

    Args:
        pod_service: Kubernetes Pod service bound to the configured cluster and
            safety policy.
        deployment_manager_service: Kubernetes Deployment service used by
            inspection and mutation tools.
        ec2_service: AWS EC2 service bound to the configured AWS or LocalStack
            environment.
        s3_service: AWS S3 service bound to the configured AWS or LocalStack
            environment.

    Returns:
        A single ordered list containing the Kubernetes and AWS tools exposed
        to the language model.

    Raises:
        ValueError: If two registered tools have the same name, which would
            make model tool selection ambiguous.

    Notes:
        Tool construction is centralized here so the FastAPI application and
        LangGraph server expose the same capabilities. Platform services are
        injected rather than created inside tools, keeping configuration and
        external clients independently testable.
    """
    tools = list(create_pod_tools(pod_service))
    tools.extend(create_s3_tools(s3_service))
    tools.extend(create_deployment_manager_tools(deployment_manager_service))
    tools.extend(create_ec2_tools(ec2_service))

    name_counts = Counter(tool.name for tool in tools)
    duplicate_names = sorted(name for name, count in name_counts.items() if count > 1)
    if duplicate_names:
        duplicates = ", ".join(duplicate_names)
        raise ValueError(f"Duplicate agent tool names: {duplicates}")

    return tools


def create_chatops_agent(
    model: BaseChatModel,
    pod_service: PodService,
    deployment_manager_service: DeploymentManagerService,
    ec2_service: EC2Service,
    s3_service: S3Service,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    audit_recorder: MutationAuditRecorder | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Create the provider-neutral LangGraph ChatOps agent.

    Args:
        model: LangChain-compatible chat model used for reasoning and tool
            selection. No provider-specific model type is required.
        pod_service: Kubernetes service backing Pod inspection and mutation
            tools.
        deployment_manager_service: Kubernetes service backing Deployment
            inspection and mutation tools.
        ec2_service: AWS service backing EC2 tools.
        s3_service: AWS service backing S3 tools.
        checkpointer: Optional LangGraph checkpoint saver used to persist thread
            state and resume human-in-the-loop interruptions.
        audit_recorder: Optional mutation audit destination. When omitted, the
            mutation middleware uses its logging-based recorder.

    Returns:
        A compiled LangGraph state graph configured with the system prompt,
        platform tools, middleware, and optional conversation checkpointer.

    Raises:
        ValueError: If the assembled tool registry contains duplicate names.

    Notes:
        Middleware bounds model calls, reduces old infrastructure output when
        the context grows, translates known provider-limit errors, audits
        executed mutations, and requires human approval for configured
        mutating tools. Approval pauses can only be resumed across requests
        when a suitable checkpointer is configured by the caller.
    """
    tools = create_chatops_tools(
        pod_service,
        deployment_manager_service,
        ec2_service,
        s3_service,
    )
    middleware: list[AgentMiddleware[Any, Any, Any]] = [
        ModelLimitErrorMiddleware(),
        ModelCallLimitMiddleware(run_limit=5, exit_behavior="end"),
        ContextEditingMiddleware(
            edits=[
                ClearToolUsesEdit(
                    trigger=3_000,
                    clear_at_least=1_500,
                    keep=2,
                    clear_tool_inputs=True,
                    placeholder=(
                        "[older infrastructure output cleared to protect "
                        "the conversation context]"
                    ),
                )
            ],
            token_count_method="approximate",
        ),
        MutationAuditMiddleware(MUTATING_TOOL_NAMES, audit_recorder),
        HumanInTheLoopMiddleware(interrupt_on=MUTATION_APPROVALS),
    ]

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=CHATOPS_SYSTEM_PROMPT,
        middleware=middleware,
        checkpointer=checkpointer,
        name="chatops-agent",
    )
