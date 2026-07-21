"""Deterministic structured audit events for executed agent mutations."""

import json
import logging
from collections.abc import Awaitable, Callable, Collection
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger("chatops.audit")


@dataclass(frozen=True)
class MutationAuditEvent:
    """Represent one executed mutation and its correlation metadata.

    Attributes:
        occurred_at: UTC timestamp recording when the outcome was observed.
        tool_name: Agent tool that performed the mutation.
        tool_call_id: LangChain identifier for the individual tool call.
        outcome: Whether tool execution succeeded or returned an error.
        arguments: Arguments supplied to the mutating tool.
        approval_decision: Human approval associated with the execution.
        thread_id: Conversation identifier when available.
        request_id: API request identifier when available.
        actor_id: Authenticated operator identifier when available.

    Notes:
        The dataclass is immutable so an audit event cannot be modified after
        it has been constructed.
    """

    occurred_at: str
    tool_name: str
    tool_call_id: str | None
    outcome: Literal["success", "error"]
    arguments: dict[str, Any]
    approval_decision: Literal["approve"] = "approve"
    thread_id: str | None = None
    request_id: str | None = None
    actor_id: str | None = None


class MutationAuditRecorder(Protocol):
    """Define the interface implemented by mutation audit destinations."""

    def record(self, event: MutationAuditEvent) -> None:
        """Persist or emit one mutation audit event.

        Args:
            event: Immutable mutation outcome to store or emit.

        Raises:
            Exception: Implementations may raise when their destination is
                unavailable. The middleware isolates those failures from tool
                execution results.
        """


class LoggingMutationAuditRecorder:
    """Emit JSON audit events through the dedicated application logger."""

    def record(self, event: MutationAuditEvent) -> None:
        """Write one mutation event to the ``chatops.audit`` logger.

        Args:
            event: Immutable mutation outcome to serialize as JSON.

        Notes:
            ``default=str`` keeps logging resilient when a tool argument uses
            a value that the standard JSON encoder cannot serialize directly.
        """
        logger.info(
            "chatops_mutation",
            extra={
                "audit_event": json.dumps(asdict(event), sort_keys=True, default=str)
            },
        )


class MutationAuditMiddleware(AgentMiddleware):
    """Audit mutation executions after HITL has allowed a tool to run.

    Read-only tools pass through without audit events. A failure in the audit
    destination is logged separately and never replaces the original tool
    result or platform exception.
    """

    def __init__(
        self,
        mutation_tool_names: Collection[str],
        recorder: MutationAuditRecorder | None = None,
    ) -> None:
        """Configure the mutation tools and destination to audit.

        Args:
            mutation_tool_names: Exact agent tool names that change platform
                state and therefore require an execution audit event.
            recorder: Destination for audit events. When omitted, events are
                emitted through ``LoggingMutationAuditRecorder``.
        """
        self._mutation_tool_names = frozenset(mutation_tool_names)
        self._recorder = recorder or LoggingMutationAuditRecorder()

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """Execute and audit a synchronous mutation tool call.

        Args:
            request: LangGraph request containing the tool name, arguments,
                identifiers, and runtime correlation metadata.
            handler: Next synchronous tool-call handler in the middleware
                chain.

        Returns:
            The original ``ToolMessage`` or graph ``Command`` produced by the
            handler without modification.

        Raises:
            Exception: Re-raises any exception produced by tool execution after
                attempting to record an error outcome.

        Notes:
            Tools not included in ``mutation_tool_names`` are passed directly
            to the next handler and are not audited by this middleware.
        """
        if request.tool_call["name"] not in self._mutation_tool_names:
            return handler(request)
        try:
            result = handler(request)
        except Exception:  # noqa: BLE001
            self._record_safely(request, "error")
            raise
        self._record_safely(request, self._result_outcome(result))
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[
            [ToolCallRequest],
            Awaitable[ToolMessage | Command[Any]],
        ],
    ) -> ToolMessage | Command[Any]:
        """Execute and audit an asynchronous mutation tool call.

        Args:
            request: LangGraph request containing the tool name, arguments,
                identifiers, and runtime correlation metadata.
            handler: Next asynchronous tool-call handler in the middleware
                chain.

        Returns:
            The awaited ``ToolMessage`` or graph ``Command`` without
            modification.

        Raises:
            Exception: Re-raises any exception produced by tool execution after
                attempting to record an error outcome.

        Notes:
            Read-only tools pass through without generating an audit event.
        """
        if request.tool_call["name"] not in self._mutation_tool_names:
            return await handler(request)
        try:
            result = await handler(request)
        except Exception:  # noqa: BLE001
            self._record_safely(request, "error")
            raise
        self._record_safely(request, self._result_outcome(result))
        return result

    def _record_safely(
        self,
        request: ToolCallRequest,
        outcome: Literal["success", "error"],
    ) -> None:
        """Record an outcome without allowing recorder failure to escape.

        Args:
            request: Tool request used to construct the audit event.
            outcome: Execution result assigned to the audit event.

        Notes:
            Recorder exceptions are written to the application logger. They do
            not change a successful tool result or hide a platform exception.
        """
        try:
            self._record(request, outcome)
        except Exception:  # noqa: BLE001
            logger.exception(
                "chatops_mutation_audit_recording_failed",
                extra={
                    "tool_name": request.tool_call["name"],
                    "tool_call_id": request.tool_call.get("id"),
                },
            )

    def _record(
        self,
        request: ToolCallRequest,
        outcome: Literal["success", "error"],
    ) -> None:
        """Build and submit one correlated mutation audit event.

        Args:
            request: Tool request containing arguments and runtime metadata.
            outcome: Execution result assigned to the audit event.

        Raises:
            Exception: Propagates failures from the configured recorder to
                ``_record_safely``, which logs and contains them.
        """
        configurable = request.runtime.config.get("configurable") or {}
        metadata = request.runtime.config.get("metadata") or {}
        self._recorder.record(
            MutationAuditEvent(
                occurred_at=datetime.now(UTC).isoformat(),
                tool_name=request.tool_call["name"],
                tool_call_id=request.tool_call.get("id"),
                outcome=outcome,
                arguments=dict(request.tool_call.get("args", {})),
                thread_id=self._correlation_value("thread_id", configurable, metadata),
                request_id=self._correlation_value(
                    "request_id", configurable, metadata
                ),
                actor_id=self._correlation_value("actor_id", configurable, metadata),
            )
        )

    @staticmethod
    def _result_outcome(
        result: ToolMessage | Command[Any],
    ) -> Literal["success", "error"]:
        """Classify a returned tool result for the audit event.

        Args:
            result: Tool message or graph command returned by execution.

        Returns:
            ``"error"`` only for a ``ToolMessage`` explicitly marked as an
            error; otherwise ``"success"``.
        """
        if isinstance(result, ToolMessage) and result.status == "error":
            return "error"
        return "success"

    @staticmethod
    def _optional_string(value: object) -> str | None:
        """Convert optional correlation metadata into a string.

        Args:
            value: Runtime correlation value of an arbitrary type.

        Returns:
            The string representation of the value, or ``None`` when absent.
        """
        return str(value) if value is not None else None

    @classmethod
    def _correlation_value(
        cls,
        key: str,
        configurable: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str | None:
        """Resolve one correlation value from graph or run configuration.

        Args:
            key: Correlation field to resolve.
            configurable: Resumable LangGraph configuration values.
            metadata: General runnable metadata used as a fallback.

        Returns:
            The correlation value converted to a string, or ``None`` when the
            field is unavailable in both sources.

        Notes:
            Resumable graph configuration takes precedence over general run
            metadata because it identifies the persisted execution context.
        """
        value = configurable.get(key)
        if value is None:
            value = metadata.get(key)
        return cls._optional_string(value)
