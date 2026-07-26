from unittest.mock import MagicMock

import pytest

from app.agent.tools.kubernetes.deployment_manager_tools import (
    create_deployment_manager_tools,
)
from app.platforms.kubernetes import KubernetesResourceNotFoundError
from app.platforms.kubernetes.models import (
    DeploymentDetails,
    DeploymentHistory,
    DeploymentMutationResult,
    DeploymentStatusSummary,
    DeploymentSummary,
    ServiceSelectorResult,
)


def test_deployment_tool_returns_handled_platform_error() -> None:
    deployment_service = MagicMock()
    deployment_service.scale_deployment.side_effect = KubernetesResourceNotFoundError(
        "demo-app/backend was not found while attempting to scale Deployment"
    )
    tools = {
        tool.name: tool for tool in create_deployment_manager_tools(deployment_service)
    }

    result = tools["scale_kubernetes_deployment"].invoke(
        {"name": "backend", "namespace": "demo-app", "replicas": 2}
    )

    assert result == (
        "Kubernetes deployment operation failed: demo-app/backend was not found "
        "while attempting to scale Deployment"
    )


def test_deployment_tool_handles_missing_required_scope() -> None:
    deployment_service = MagicMock()
    tools = {
        tool.name: tool for tool in create_deployment_manager_tools(deployment_service)
    }

    result = tools["scale_kubernetes_deployment"].invoke({"replicas": 2})

    assert result.startswith("Kubernetes deployment operation could not run")
    deployment_service.scale_deployment.assert_not_called()


@pytest.mark.parametrize(
    ("tool_name", "service_method", "tool_args", "service_result"),
    [
        (
            "list_kubernetes_deployments",
            "list_deployments",
            {"namespace": "demo-app"},
            [
                DeploymentSummary(
                    name="backend",
                    namespace="demo-app",
                    desired_replicas=2,
                    ready_replicas=2,
                    available_replicas=2,
                    updated_replicas=2,
                )
            ],
        ),
        (
            "get_kubernetes_deployment",
            "get_deployment",
            {"name": "backend", "namespace": "demo-app"},
            DeploymentDetails(
                name="backend",
                namespace="demo-app",
                desired_replicas=2,
                ready_replicas=2,
                available_replicas=2,
                updated_replicas=2,
            ),
        ),
        (
            "get_kubernetes_deployment_status",
            "get_deployment_status",
            {"name": "backend", "namespace": "demo-app"},
            DeploymentStatusSummary(
                name="backend",
                namespace="demo-app",
                rollout_state="complete",
                desired_replicas=2,
                ready_replicas=2,
                available_replicas=2,
                updated_replicas=2,
            ),
        ),
        (
            "get_kubernetes_deployment_history",
            "get_deployment_history",
            {"name": "backend", "namespace": "demo-app"},
            DeploymentHistory(
                deployment_name="backend",
                namespace="demo-app",
            ),
        ),
        *[
            (
                tool_name,
                service_method,
                tool_args,
                DeploymentMutationResult(
                    deployment_name="backend",
                    namespace="demo-app",
                    operation=operation,
                    message="Read current Deployment state to verify the outcome.",
                ),
            )
            for tool_name, service_method, tool_args, operation in [
                (
                    "create_kubernetes_deployment",
                    "create_deployment",
                    {
                        "name": "backend",
                        "namespace": "demo-app",
                        "image": "nginx:alpine",
                    },
                    "create",
                ),
                (
                    "delete_kubernetes_deployment",
                    "delete_deployment",
                    {"name": "backend", "namespace": "demo-app"},
                    "delete",
                ),
                (
                    "scale_kubernetes_deployment",
                    "scale_deployment",
                    {"name": "backend", "namespace": "demo-app", "replicas": 2},
                    "scale",
                ),
                (
                    "restart_kubernetes_deployment",
                    "restart_deployment",
                    {"name": "backend", "namespace": "demo-app"},
                    "restart",
                ),
                (
                    "update_kubernetes_deployment_image",
                    "update_deployment_image",
                    {
                        "name": "backend",
                        "namespace": "demo-app",
                        "container_name": "backend",
                        "new_image": "example/backend:v2",
                    },
                    "update_image",
                ),
                (
                    "rollback_kubernetes_deployment",
                    "rollback_deployment",
                    {"name": "backend", "namespace": "demo-app", "revision": 1},
                    "rollback",
                ),
                (
                    "pause_kubernetes_deployment",
                    "pause_deployment",
                    {"name": "backend", "namespace": "demo-app"},
                    "pause",
                ),
                (
                    "resume_kubernetes_deployment",
                    "resume_deployment",
                    {"name": "backend", "namespace": "demo-app"},
                    "resume",
                ),
            ]
        ],
        (
            "verify_kubernetes_service_selector",
            "verify_service_selector",
            {"service_name": "backend", "namespace": "demo-app"},
            ServiceSelectorResult(
                service_name="backend",
                namespace="demo-app",
                status="ok",
                selector={"app": "backend"},
                matched_pods=["backend-123"],
                running_pods=["backend-123"],
                message="One running Pod matches.",
            ),
        ),
    ],
)
def test_every_deployment_tool_returns_string_observation(
    tool_name: str,
    service_method: str,
    tool_args: dict[str, object],
    service_result: object,
) -> None:
    deployment_service = MagicMock()
    getattr(deployment_service, service_method).return_value = service_result
    tools = {
        tool.name: tool for tool in create_deployment_manager_tools(deployment_service)
    }

    result = tools[tool_name].invoke(tool_args)

    assert isinstance(result, str)
    assert result
