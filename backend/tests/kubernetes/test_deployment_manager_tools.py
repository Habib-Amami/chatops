from unittest.mock import MagicMock

from app.agent.tools.kubernetes.deployment_manager_tools import (
    create_deployment_manager_tools,
)
from app.platforms.kubernetes import KubernetesResourceNotFoundError


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
