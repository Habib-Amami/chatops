import asyncio
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from app.agent.middleware import (
    ModelLimitErrorMiddleware,
    MutationAuditEvent,
    MutationAuditMiddleware,
    get_model_limit_message,
)


class FakeProviderError(Exception):
    """Provider-shaped exception used without importing a specific SDK."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_model_limit_middleware_returns_readable_413_message() -> None:
    middleware = ModelLimitErrorMiddleware()
    request = cast(ModelRequest[Any], None)

    def failing_handler(_: ModelRequest[Any]) -> ModelResponse[Any]:
        raise FakeProviderError(413, "Request too large for token limit")

    result = middleware.wrap_model_call(request, failing_handler)

    assert isinstance(result, AIMessage)
    assert "too large" in str(result.content)
    assert "new thread" in str(result.content)


def test_model_limit_middleware_handles_async_rate_limit() -> None:
    middleware = ModelLimitErrorMiddleware()
    request = cast(ModelRequest[Any], None)

    async def failing_handler(_: ModelRequest[Any]) -> ModelResponse[Any]:
        raise FakeProviderError(429, "rate_limit_exceeded")

    async def invoke() -> ModelResponse[Any] | AIMessage:
        return await middleware.awrap_model_call(request, failing_handler)

    result = asyncio.run(invoke())

    assert isinstance(result, AIMessage)
    assert "quota" in str(result.content)


def test_model_limit_message_detects_provider_quota_error_code() -> None:
    class FakeQuotaError(Exception):
        code = 429

    error = FakeQuotaError("RESOURCE_EXHAUSTED: quota exceeded")

    message = get_model_limit_message(error)

    assert message is not None
    assert "quota" in message


def test_model_limit_middleware_does_not_hide_unknown_errors() -> None:
    middleware = ModelLimitErrorMiddleware()
    request = cast(ModelRequest[Any], None)

    def failing_handler(_: ModelRequest[Any]) -> ModelResponse[Any]:
        raise RuntimeError("unexpected provider failure")

    with pytest.raises(RuntimeError, match="unexpected provider failure"):
        middleware.wrap_model_call(request, failing_handler)


def test_model_limit_message_detects_provider_text_fallback() -> None:
    error = RuntimeError("request too large: context token budget exceeded")

    assert get_model_limit_message(error) is not None


def test_model_limit_message_handles_provider_tool_content_error() -> None:
    error = FakeProviderError(
        400,
        "'messages.3': for 'role:tool', content value must be a string",
    )

    message = get_model_limit_message(error)

    assert message is not None
    assert "tool result" in message
    assert "messages.3" not in message


def _mutation_request(config: dict[str, Any]) -> ToolCallRequest:
    runtime = MagicMock()
    runtime.config = config
    return ToolCallRequest(
        tool_call=cast(
            Any,
            {
                "name": "delete_kubernetes_pod",
                "args": {"name": "test-pod", "namespace": "chatops-demo"},
                "id": "delete-call-1",
                "type": "tool_call",
            },
        ),
        tool=None,
        state={},
        runtime=runtime,
    )


def test_mutation_audit_uses_metadata_as_correlation_fallback() -> None:
    recorder = MagicMock()
    middleware = MutationAuditMiddleware({"delete_kubernetes_pod"}, recorder)
    request = _mutation_request(
        {
            "configurable": {"thread_id": "thread-1"},
            "metadata": {
                "request_id": "request-1",
                "actor_id": "operator-1",
            },
        }
    )
    expected = ToolMessage(content="deleted", tool_call_id="delete-call-1")

    result = middleware.wrap_tool_call(request, lambda _: expected)

    assert result is expected
    event = recorder.record.call_args.args[0]
    assert isinstance(event, MutationAuditEvent)
    assert event.thread_id == "thread-1"
    assert event.request_id == "request-1"
    assert event.actor_id == "operator-1"


def test_mutation_audit_recorder_failure_does_not_change_tool_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = MagicMock()
    recorder.record.side_effect = RuntimeError("audit database unavailable")
    middleware = MutationAuditMiddleware({"delete_kubernetes_pod"}, recorder)
    request = _mutation_request({"configurable": {"thread_id": "thread-1"}})
    expected = ToolMessage(content="deleted", tool_call_id="delete-call-1")

    with caplog.at_level("ERROR", logger="chatops.audit"):
        result = middleware.wrap_tool_call(request, lambda _: expected)

    assert result is expected
    assert "chatops_mutation_audit_recording_failed" in caplog.text


def test_async_mutation_audit_recorder_failure_preserves_platform_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = MagicMock()
    recorder.record.side_effect = RuntimeError("audit database unavailable")
    middleware = MutationAuditMiddleware({"delete_kubernetes_pod"}, recorder)
    request = _mutation_request({"configurable": {"thread_id": "thread-1"}})

    async def failing_handler(_: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("Kubernetes delete failed")

    async def invoke() -> ToolMessage:
        return cast(
            ToolMessage,
            await middleware.awrap_tool_call(request, failing_handler),
        )

    with caplog.at_level("ERROR", logger="chatops.audit"):
        with pytest.raises(RuntimeError, match="Kubernetes delete failed"):
            asyncio.run(invoke())

    assert "chatops_mutation_audit_recording_failed" in caplog.text
