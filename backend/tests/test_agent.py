from typing import Any
from unittest.mock import MagicMock

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage

from app.agent import create_chatops_agent
from app.agent.tools.kubernetes import create_pod_tools
from app.platforms.kubernetes.services import (
    PodConditionSummary,
    PodContainerSummary,
    PodDetails,
    PodEventSummary,
    PodSummary,
)


class ToolCallingFakeChatModel(GenericFakeChatModel):
    """Generic fake model that accepts tools for an agent-loop test."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ToolCallingFakeChatModel":
        return self


def _pod_tools_by_name(pod_service: MagicMock) -> dict[str, Any]:
    return {tool.name: tool for tool in create_pod_tools(pod_service)}


def test_pod_tool_returns_agent_friendly_summary() -> None:
    pod_service = MagicMock()
    pod_service.get_pods.return_value = [
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
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pods"]

    result = pod_tool.invoke({"namespace": "chatops-demo"})

    assert result == (
        "Pods in namespace 'chatops-demo':\n"
        "- api-123: Running, ready, restarts=0, node=minikube, "
        "ip=10.244.0.10, images=example/api:1.0"
    )
    pod_service.get_pods.assert_called_once_with("chatops-demo")


def test_pod_details_tool_returns_agent_friendly_summary() -> None:
    pod_service = MagicMock()
    pod_service.get_pod.return_value = PodDetails(
        name="api-123",
        namespace="chatops-demo",
        phase="Running",
        ready=False,
        restart_count=3,
        node_name="minikube",
        pod_ip="10.244.0.10",
        images=["example/api:1.0"],
        labels={"app": "api"},
        created_at="2026-01-02T03:04:05+00:00",
        containers=[
            PodContainerSummary(
                name="api",
                image="example/api:1.0",
                ready=False,
                restart_count=3,
            )
        ],
        conditions=[
            PodConditionSummary(
                type="Ready",
                status="False",
                reason="ContainersNotReady",
                message="container api is not ready",
            )
        ],
    )
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pod"]

    result = pod_tool.invoke(
        {"namespace": "chatops-demo", "pod_name": "api-123"}
    )

    assert "Pod 'api-123' in namespace 'chatops-demo':" in result
    assert "Ready: no" in result
    assert "- api: image=example/api:1.0, not ready, restarts=3" in result
    assert "Ready: status=False, reason=ContainersNotReady" in result
    pod_service.get_pod.assert_called_once_with(
        "chatops-demo",
        "api-123",
    )


def test_pod_logs_tool_returns_recent_logs() -> None:
    pod_service = MagicMock()
    pod_service.get_pod_logs.return_value = "2026-01-02 error"
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pod_logs"]

    result = pod_tool.invoke(
        {
            "namespace": "chatops-demo",
            "pod_name": "api-123",
            "container": "api",
            "tail_lines": 25,
        }
    )

    assert result == (
        "Recent logs for pod 'api-123' in namespace 'chatops-demo':\n"
        "2026-01-02 error"
    )
    pod_service.get_pod_logs.assert_called_once_with(
        "chatops-demo",
        "api-123",
        container="api",
        tail_lines=25,
    )


def test_describe_pod_tool_returns_details_with_events() -> None:
    pod_service = MagicMock()
    pod_service.get_pod.return_value = PodDetails(
        name="api-123",
        namespace="chatops-demo",
        phase="Running",
        ready=False,
        restart_count=3,
        node_name="minikube",
        pod_ip="10.244.0.10",
        images=["example/api:1.0"],
        labels={},
        created_at=None,
        containers=[],
        conditions=[],
    )
    pod_service.get_pod_events.return_value = [
        PodEventSummary(
            type="Warning",
            reason="BackOff",
            message="Back-off restarting failed container",
            count=3,
            first_timestamp="2026-01-02T03:04:05+00:00",
            last_timestamp="2026-01-02T03:05:05+00:00",
        )
    ]
    pod_tool = _pod_tools_by_name(pod_service)["describe_kubernetes_pod"]

    result = pod_tool.invoke(
        {"namespace": "chatops-demo", "pod_name": "api-123"}
    )

    assert "Pod 'api-123' in namespace 'chatops-demo':" in result
    assert "Events:" in result
    assert (
        "- Warning BackOff: Back-off restarting failed container "
        "(count=3, last_seen=2026-01-02T03:05:05+00:00)"
    ) in result
    pod_service.get_pod.assert_called_once_with(
        "chatops-demo",
        "api-123",
    )
    pod_service.get_pod_events.assert_called_once_with(
        "chatops-demo",
        "api-123",
    )


def test_agent_executes_pod_tool_without_live_model() -> None:
    pod_service = MagicMock()
    pod_service.get_pods.return_value = [
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
                            "name": "get_kubernetes_pods",
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
    agent = create_chatops_agent(model, pod_service)

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
    pod_service.get_pods.assert_called_once_with("chatops-demo")
