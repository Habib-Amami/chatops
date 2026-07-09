from typing import Any
from unittest.mock import MagicMock

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage

from app.agent import create_chatops_agent
from app.agent.tools.kubernetes import create_pod_tools
from app.platforms.kubernetes.services import PodSummary


class ToolCallingFakeChatModel(GenericFakeChatModel):
    """Generic fake model that accepts tools for an agent-loop test."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ToolCallingFakeChatModel":
        return self


def test_pod_tool_returns_serializable_summaries() -> None:
    pod_service = MagicMock()
    pod_service.list_pods.return_value = [
        PodSummary(
            name="api-123",
            namespace="chatops-demo",
            phase="Running",
            ready=True,
            restart_count=0,
            node_name="minikube",
            pod_ip="10.244.0.10",
            images=["example/api:1.0"],
        )
    ]
    pod_tool = create_pod_tools(pod_service)[0]

    result = pod_tool.invoke({"namespace": "chatops-demo"})

    assert result == [
        {
            "name": "api-123",
            "namespace": "chatops-demo",
            "phase": "Running",
            "ready": True,
            "restart_count": 0,
            "node_name": "minikube",
            "pod_ip": "10.244.0.10",
            "images": ["example/api:1.0"],
        }
    ]
    pod_service.list_pods.assert_called_once_with("chatops-demo")


def test_agent_executes_pod_tool_without_live_model() -> None:
    pod_service = MagicMock()
    pod_service.list_pods.return_value = [
        PodSummary(
            name="api-123",
            namespace="chatops-demo",
            phase="Running",
            ready=True,
            restart_count=0,
            node_name="minikube",
            pod_ip="10.244.0.10",
            images=["example/api:1.0"],
        )
    ]
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "list_kubernetes_pods",
                            "args": {"namespace": "chatops-demo"},
                            "id": "pod-call-1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The api-123 pod is running and ready."),
            ]
        )
    )
    deployment_manager_service = MagicMock()
    agent = create_chatops_agent(model, pod_service, deployment_manager_service)

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "List pods in chatops-demo",
                }
            ]
        }
    )

    assert result["messages"][-1].content == (
        "The api-123 pod is running and ready."
    )
    assert any(isinstance(message, ToolMessage) for message in result["messages"])
    pod_service.list_pods.assert_called_once_with("chatops-demo")
