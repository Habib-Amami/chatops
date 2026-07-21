from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent import create_chatops_agent, create_chatops_tools
from app.agent.middleware import MutationAuditEvent
from app.agent.tools.kubernetes.formatters import (
    LOG_TRUNCATION_MARKER,
    MAX_LOG_CHARACTERS,
)
from app.agent.tools.kubernetes import create_pod_tools
from app.platforms.kubernetes import KubernetesOperationError
from app.platforms.kubernetes.models import (
    PodConditionSummary,
    PodContainerStateSummary,
    PodContainerSummary,
    PodCreateResult,
    PodDeleteResult,
    PodDetails,
    PodEventSummary,
    PodOwnerSummary,
    PodStatusDiagnosis,
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
        init_containers=[
            PodContainerSummary(
                name="migrate",
                image="example/migrate:1.0",
                ready=True,
                restart_count=0,
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
        owners=[
            PodOwnerSummary(
                kind="ReplicaSet",
                name="api-7b96f6dcb5",
                uid="owner-uid",
                controller=True,
            )
        ],
    )
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pod"]

    result = pod_tool.invoke({"namespace": "chatops-demo", "pod_name": "api-123"})

    assert "Pod 'api-123' in namespace 'chatops-demo':" in result
    assert "Ready: no" in result
    assert "Owners: ReplicaSet/api-7b96f6dcb5 (controller)" in result
    assert "- api: image=example/api:1.0, not ready, restarts=3" in result
    assert "- migrate: image=example/migrate:1.0, ready, restarts=0" in result
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
        "Recent logs for pod 'api-123' in namespace 'chatops-demo':\n2026-01-02 error"
    )
    pod_service.get_pod_logs.assert_called_once_with(
        "chatops-demo",
        "api-123",
        container="api",
        tail_lines=25,
        previous=False,
        since_seconds=None,
    )


def test_pod_logs_tool_uses_a_safe_default_window() -> None:
    pod_service = MagicMock()
    pod_service.get_pod_logs.return_value = "recent log"
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pod_logs"]

    pod_tool.invoke(
        {
            "namespace": "chatops-demo",
            "pod_name": "api-123",
        }
    )

    pod_service.get_pod_logs.assert_called_once_with(
        "chatops-demo",
        "api-123",
        container=None,
        tail_lines=50,
        previous=False,
        since_seconds=None,
    )


def test_pod_logs_tool_truncates_oversized_output_from_the_oldest_end() -> None:
    logs = "\n".join(
        f"line-{line_number:03d} " + ("x" * 100) for line_number in range(100)
    )
    pod_service = MagicMock()
    pod_service.get_pod_logs.return_value = logs
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pod_logs"]

    result = pod_tool.invoke({"namespace": "chatops-demo", "pod_name": "api-123"})

    formatted_logs = result.split("\n", 1)[1]
    assert len(formatted_logs) <= MAX_LOG_CHARACTERS
    assert LOG_TRUNCATION_MARKER in result
    assert "line-000" not in result
    assert "line-099" in result


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

    result = pod_tool.invoke({"namespace": "chatops-demo", "pod_name": "api-123"})

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


def test_pod_events_tool_returns_agent_friendly_events() -> None:
    pod_service = MagicMock()
    pod_service.get_pod_events.return_value = [
        PodEventSummary(
            type="Warning",
            reason="FailedScheduling",
            message="Insufficient memory",
            count=2,
            first_timestamp=None,
            last_timestamp="2026-01-02T03:05:05+00:00",
        )
    ]
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pod_events"]

    result = pod_tool.invoke({"pod_name": "api-123", "namespace": "chatops-demo"})

    assert result == (
        "Events for pod 'api-123' in namespace 'chatops-demo':\n"
        "- Warning FailedScheduling: Insufficient memory "
        "(count=2, last_seen=2026-01-02T03:05:05+00:00)"
    )
    pod_service.get_pod_events.assert_called_once_with(
        "chatops-demo",
        "api-123",
        limit=20,
    )


def test_pod_logs_tool_can_request_previous_logs() -> None:
    pod_service = MagicMock()
    pod_service.get_pod_logs.return_value = "previous crash"
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pod_logs"]

    result = pod_tool.invoke(
        {
            "namespace": "chatops-demo",
            "pod_name": "api-123",
            "container": "api",
            "tail_lines": 50,
            "previous": True,
            "since_seconds": 3600,
        }
    )

    assert result == (
        "Previous logs for pod 'api-123' in namespace 'chatops-demo':\nprevious crash"
    )
    pod_service.get_pod_logs.assert_called_once_with(
        "chatops-demo",
        "api-123",
        container="api",
        tail_lines=50,
        previous=True,
        since_seconds=3600,
    )


def test_pod_tool_returns_normalized_platform_error() -> None:
    pod_service = MagicMock()
    pod_service.get_pods.side_effect = KubernetesOperationError(
        "Could not contact the Kubernetes API"
    )
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pods"]

    result = pod_tool.invoke({"namespace": "chatops-demo"})

    assert result == (
        "Kubernetes operation failed: Could not contact the Kubernetes API"
    )


def test_pod_tool_returns_namespace_policy_denial() -> None:
    pod_service = MagicMock()
    pod_service.get_pods.side_effect = PermissionError(
        "Namespace 'kube-system' is not allowed"
    )
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pods"]

    result = pod_tool.invoke({"namespace": "kube-system"})

    assert result == (
        "Kubernetes operation failed: Namespace 'kube-system' is not allowed"
    )


def test_pod_tool_handles_missing_required_namespace() -> None:
    pod_service = MagicMock()
    pod_tool = _pod_tools_by_name(pod_service)["get_kubernetes_pods"]

    result = pod_tool.invoke({})

    assert result == (
        "Kubernetes operation could not run because required parameters were "
        "missing or invalid. Do not retry until every required resource name "
        "and namespace is known."
    )
    pod_service.get_pods.assert_not_called()


def test_pod_status_tool_returns_formatted_diagnosis() -> None:
    pod_service = MagicMock()
    pod_service.diagnose_pod_status.return_value = PodStatusDiagnosis(
        pod_name="api-123",
        namespace="chatops-demo",
        phase="Pending",
        containers=[
            PodContainerStateSummary(
                name="api",
                ready=False,
                restart_count=1,
                state="Waiting",
                reason="ImagePullBackOff",
            )
        ],
    )
    pod_tool = _pod_tools_by_name(pod_service)["diagnose_kubernetes_pod_status"]

    result = pod_tool.invoke({"pod_name": "api-123", "namespace": "chatops-demo"})

    assert result == (
        "Status diagnosis for pod 'api-123' in namespace 'chatops-demo':\n"
        "Phase: Pending\n"
        "Reason: none\n"
        "Message: none\n"
        "Containers:\n"
        "- container/api: Waiting, reason=ImagePullBackOff, not ready, "
        "restarts=1, last_state=none"
    )
    pod_service.diagnose_pod_status.assert_called_once_with(
        "chatops-demo",
        "api-123",
    )


def test_delete_pod_tool_returns_compact_acknowledgement() -> None:
    pod_service = MagicMock()
    pod_service.delete_pod.return_value = PodDeleteResult(
        pod_name="api-123",
        namespace="chatops-demo",
        status="deleted",
        deleted=True,
    )
    pod_tool = _pod_tools_by_name(pod_service)["delete_kubernetes_pod"]

    result = pod_tool.invoke({"name": "api-123", "namespace": "chatops-demo"})

    assert result == (
        "Kubernetes accepted deletion of pod 'api-123' in namespace "
        "'chatops-demo': verification_status=deleted, deleted=yes."
    )
    pod_service.delete_pod.assert_called_once_with(
        "chatops-demo",
        "api-123",
    )


def test_create_pod_tool_returns_compact_acknowledgement() -> None:
    pod_service = MagicMock()
    pod_service.create_pod.return_value = PodCreateResult(
        pod_name="manual-test",
        namespace="chatops-demo",
        image="docker.io/nginxinc/nginx-unprivileged:alpine",
        registry="docker.io",
        status="ready",
        phase="Running",
        ready=True,
    )
    pod_tool = _pod_tools_by_name(pod_service)["create_kubernetes_pod"]

    result = pod_tool.invoke(
        {
            "name": "manual-test",
            "namespace": "chatops-demo",
        }
    )

    assert result == (
        "Kubernetes accepted standalone pod 'manual-test' in namespace "
        "'chatops-demo': image=docker.io/nginxinc/nginx-unprivileged:alpine, "
        "registry=docker.io, manifest_verified=yes, "
        "verification_status=ready, phase=Running, ready=yes."
    )
    pod_service.create_pod.assert_called_once_with(
        "chatops-demo",
        "manual-test",
        "nginxinc/nginx-unprivileged:alpine",
        None,
    )


def test_agent_tool_registry_has_unique_names() -> None:
    tools = create_chatops_tools(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    names = [tool.name for tool in tools]

    assert len(names) == 18
    assert len(names) == len(set(names))
    assert "list_s3_buckets" in names
    assert "list_s3_objects" in names
    assert "save_chat_log" not in names
    assert "save_audit_log" not in names


def test_agent_tool_registry_rejects_duplicate_names() -> None:
    duplicate_tool = create_pod_tools(MagicMock())[0]

    with patch(
        "app.agent.agent.create_deployment_manager_tools",
        return_value=[duplicate_tool],
    ):
        with pytest.raises(
            ValueError,
            match="Duplicate agent tool names: get_kubernetes_pods",
        ):
            create_chatops_tools(MagicMock(), MagicMock(), MagicMock(), MagicMock())


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
    deployment_manager_service = MagicMock()
    ec2_service = MagicMock()
    agent = create_chatops_agent(
        model,
        pod_service,
        deployment_manager_service,
        ec2_service,
        MagicMock(),
    )

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

    assert result["messages"][-1].content == ("The api-123 pod is running and ready.")
    assert any(isinstance(message, ToolMessage) for message in result["messages"])
    pod_service.get_pods.assert_called_once_with("chatops-demo")


def test_agent_stops_repeated_invalid_tool_recovery() -> None:
    pod_service = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_kubernetes_pods",
                            "args": {},
                            "id": f"invalid-pod-call-{index}",
                            "type": "tool_call",
                        }
                    ],
                )
                for index in range(6)
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        pod_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

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

    assert "Model call limits exceeded" in result["messages"][-1].content
    pod_service.get_pods.assert_not_called()


def test_agent_requires_approval_before_pod_deletion() -> None:
    pod_service = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_kubernetes_pod",
                            "args": {
                                "name": "api-123",
                                "namespace": "chatops-demo",
                            },
                            "id": "pod-delete-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        pod_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Delete api-123 in chatops-demo",
                }
            ]
        }
    )

    assert "__interrupt__" in result
    interrupt = result["__interrupt__"][0].value
    assert interrupt["action_requests"][0]["name"] == "delete_kubernetes_pod"
    assert interrupt["action_requests"][0]["args"] == {
        "name": "api-123",
        "namespace": "chatops-demo",
    }
    assert interrupt["review_configs"][0]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    pod_service.delete_pod.assert_not_called()


def test_agent_requires_approval_before_pod_creation() -> None:
    pod_service = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "create_kubernetes_pod",
                            "args": {
                                "name": "manual-test",
                                "namespace": "chatops-demo",
                                "image": "nginx:alpine",
                            },
                            "id": "pod-create-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        pod_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Create manual-test in chatops-demo",
                }
            ]
        }
    )

    assert "__interrupt__" in result
    interrupt = result["__interrupt__"][0].value
    assert interrupt["action_requests"][0]["name"] == "create_kubernetes_pod"
    assert interrupt["action_requests"][0]["args"] == {
        "name": "manual-test",
        "namespace": "chatops-demo",
        "image": "nginx:alpine",
    }
    assert interrupt["review_configs"][0]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    pod_service.create_pod.assert_not_called()


def test_agent_executes_pod_creation_once_after_approval() -> None:
    pod_service = MagicMock()
    pod_service.create_pod.return_value = PodCreateResult(
        pod_name="manual-test",
        namespace="chatops-demo",
        image="docker.io/library/nginx:alpine",
        registry="docker.io",
        status="ready",
        phase="Running",
        ready=True,
    )
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "create_kubernetes_pod",
                            "args": {
                                "name": "manual-test",
                                "namespace": "chatops-demo",
                                "image": "nginx:alpine",
                            },
                            "id": "pod-create-approved",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The standalone Pod creation was requested."),
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        pod_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "approve-pod-create"}}

    interrupted = agent.invoke(
        {"messages": [{"role": "user", "content": "Create manual-test"}]},
        config=config,
    )
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
    )

    assert "__interrupt__" in interrupted
    assert result["messages"][-1].content == (
        "The standalone Pod creation was requested."
    )
    pod_service.create_pod.assert_called_once_with(
        "chatops-demo",
        "manual-test",
        "nginx:alpine",
        None,
    )


def test_agent_does_not_create_pod_after_rejection() -> None:
    pod_service = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "create_kubernetes_pod",
                            "args": {
                                "name": "manual-test",
                                "namespace": "chatops-demo",
                                "image": "nginx:alpine",
                            },
                            "id": "pod-create-rejected",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Pod creation was cancelled."),
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        pod_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "reject-pod-create"}}

    agent.invoke(
        {"messages": [{"role": "user", "content": "Create manual-test"}]},
        config=config,
    )
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "reject"}]}),
        config=config,
    )

    assert "__interrupt__" not in result
    assert result["messages"][-1].content == "Pod creation was cancelled."
    pod_service.create_pod.assert_not_called()


def test_agent_executes_pod_deletion_once_after_approval() -> None:
    pod_service = MagicMock()
    pod_service.delete_pod.return_value = PodDeleteResult(
        pod_name="manual-test",
        namespace="chatops-demo",
        status="deleted",
        deleted=True,
    )
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_kubernetes_pod",
                            "args": {
                                "name": "manual-test",
                                "namespace": "chatops-demo",
                            },
                            "id": "pod-delete-approved",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The Pod deletion was requested."),
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        pod_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "approve-pod-delete"}}

    agent.invoke(
        {"messages": [{"role": "user", "content": "Delete manual-test"}]},
        config=config,
    )
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
    )

    assert result["messages"][-1].content == "The Pod deletion was requested."
    pod_service.delete_pod.assert_called_once_with("chatops-demo", "manual-test")


def test_agent_does_not_delete_pod_after_rejection() -> None:
    pod_service = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "delete_kubernetes_pod",
                            "args": {
                                "name": "manual-test",
                                "namespace": "chatops-demo",
                            },
                            "id": "pod-delete-rejected",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Pod deletion was cancelled."),
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        pod_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": "reject-pod-delete"}}

    agent.invoke(
        {"messages": [{"role": "user", "content": "Delete manual-test"}]},
        config=config,
    )
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "reject"}]}),
        config=config,
    )

    assert "__interrupt__" not in result
    assert result["messages"][-1].content == "Pod deletion was cancelled."
    pod_service.delete_pod.assert_not_called()


@pytest.mark.parametrize(
    ("tool_name", "tool_args", "service_method"),
    [
        (
            "scale_kubernetes_deployment",
            {"name": "api", "namespace": "chatops-demo", "replicas": 2},
            "scale_deployment",
        ),
        (
            "restart_kubernetes_deployment",
            {"name": "api", "namespace": "chatops-demo"},
            "restart_deployment",
        ),
        (
            "update_kubernetes_deployment_image",
            {
                "name": "api",
                "namespace": "chatops-demo",
                "container_name": "api",
                "new_image": "example/api:v2",
            },
            "update_deployment_image",
        ),
        (
            "rollback_kubernetes_deployment",
            {"name": "api", "namespace": "chatops-demo", "revision": 2},
            "rollback_deployment",
        ),
        (
            "pause_kubernetes_deployment",
            {"name": "api", "namespace": "chatops-demo"},
            "pause_deployment",
        ),
        (
            "resume_kubernetes_deployment",
            {"name": "api", "namespace": "chatops-demo"},
            "resume_deployment",
        ),
    ],
)
def test_agent_requires_approval_before_every_deployment_mutation(
    tool_name: str,
    tool_args: dict[str, object],
    service_method: str,
) -> None:
    deployment_service = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": tool_name,
                            "args": tool_args,
                            "id": f"{tool_name}-approval",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        MagicMock(),
        deployment_service,
        MagicMock(),
        MagicMock(),
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Perform the mutation"}]}
    )

    assert "__interrupt__" in result
    interrupt = result["__interrupt__"][0].value
    assert interrupt["action_requests"][0]["name"] == tool_name
    assert interrupt["action_requests"][0]["args"] == tool_args
    assert interrupt["review_configs"][0]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    getattr(deployment_service, service_method).assert_not_called()


def test_agent_executes_approved_deployment_mutation_once_and_audits_it() -> None:
    deployment_service = MagicMock()
    deployment_service.scale_deployment.return_value = {
        "deployment": "api",
        "replicas": 2,
    }
    audit_recorder = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "scale_kubernetes_deployment",
                            "args": {
                                "name": "api",
                                "namespace": "chatops-demo",
                                "replicas": 2,
                            },
                            "id": "deployment-scale-approved",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The Deployment was scaled."),
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        MagicMock(),
        deployment_service,
        MagicMock(),
        MagicMock(),
        checkpointer=InMemorySaver(),
        audit_recorder=audit_recorder,
    )
    config: RunnableConfig = {
        "configurable": {
            "thread_id": "deployment-approval-thread",
            "request_id": "deployment-request",
            "actor_id": "operator-1",
        }
    }

    agent.invoke(
        {"messages": [{"role": "user", "content": "Scale api to two replicas"}]},
        config=config,
    )
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config,
    )

    assert result["messages"][-1].content == "The Deployment was scaled."
    deployment_service.scale_deployment.assert_called_once_with(
        name="api",
        namespace="chatops-demo",
        replicas=2,
    )
    audit_recorder.record.assert_called_once()
    event = audit_recorder.record.call_args.args[0]
    assert isinstance(event, MutationAuditEvent)
    assert event.tool_name == "scale_kubernetes_deployment"
    assert event.outcome == "success"
    assert event.thread_id == "deployment-approval-thread"
    assert event.request_id == "deployment-request"
    assert event.actor_id == "operator-1"


def test_agent_does_not_execute_or_audit_rejected_deployment_mutation() -> None:
    deployment_service = MagicMock()
    audit_recorder = MagicMock()
    model = ToolCallingFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "scale_kubernetes_deployment",
                            "args": {
                                "name": "api",
                                "namespace": "chatops-demo",
                                "replicas": 2,
                            },
                            "id": "deployment-scale-rejected",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="The Deployment scaling was cancelled."),
            ]
        )
    )
    agent = create_chatops_agent(
        model,
        MagicMock(),
        deployment_service,
        MagicMock(),
        MagicMock(),
        checkpointer=InMemorySaver(),
        audit_recorder=audit_recorder,
    )
    config: RunnableConfig = {
        "configurable": {"thread_id": "deployment-rejection-thread"}
    }

    agent.invoke(
        {"messages": [{"role": "user", "content": "Scale api to two replicas"}]},
        config=config,
    )
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "reject"}]}),
        config=config,
    )

    assert "__interrupt__" not in result
    assert result["messages"][-1].content == ("The Deployment scaling was cancelled.")
    deployment_service.scale_deployment.assert_not_called()
    audit_recorder.record.assert_not_called()
