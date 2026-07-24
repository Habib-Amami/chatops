"""Model middleware for user-facing provider limit failures."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage


def get_model_limit_message(error: Exception) -> str | None:
    """Translate a known model-provider limit error into a safe chat message.

    Args:
        error: Exception raised by the configured model provider or its client.

    Returns:
        A user-facing explanation for recognized request-size or quota errors,
        or ``None`` when the exception is not a known provider-limit failure.

    Notes:
        Detection uses both HTTP-like status attributes and common provider
        error text so the agent remains independent of a specific model SDK.
        Returning ``None`` tells callers to preserve the original exception.
    """
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(error, "code", None)
    error_text = str(error).lower()

    if status_code == 413 or (
        "request too large" in error_text
        and ("token" in error_text or "context" in error_text)
    ):
        return (
            "The conversation and infrastructure output are too large for the "
            "configured model. Start a new thread or request a smaller log "
            "window, such as the last 20 lines."
        )

    if status_code == 429 or any(
        marker in error_text
        for marker in (
            "rate_limit_exceeded",
            "resource_exhausted",
            "quota exceeded",
            "too many requests",
        )
    ):
        return (
            "The configured model's request quota was reached. Wait for the "
            "provider quota to reset or switch to a model or API key with "
            "available quota, then retry."
        )

    if status_code == 400 and "role:tool" in error_text and "content" in error_text:
        return (
            "The model received an empty tool result, which is not supported by "
            "this provider. This can happen when a Kubernetes or AWS tool returns "
            "no data. Please try rephrasing your request or targeting a resource "
            "that exists in the cluster."
        )

    return None


class ModelLimitErrorMiddleware(AgentMiddleware):
    """Convert known model-provider limit failures into assistant messages.

    Only request-size and rate/quota failures are handled. All other
    exceptions are re-raised so configuration, networking, and programming
    errors remain visible to the application's normal error handling.
    """

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        """Wrap a synchronous model call with provider-limit translation.

        Args:
            request: LangChain model request being processed by the agent.
            handler: Next synchronous model-call handler in the middleware
                chain.

        Returns:
            The original model response when the call succeeds, or an
            ``AIMessage`` explaining a recognized provider limit.

        Raises:
            Exception: Re-raises the original exception when it is not a known
                request-size or rate/quota failure.
        """
        try:
            return handler(request)
        except Exception as error:  # noqa: BLE001
            message = get_model_limit_message(error)
            if message is None:
                raise
            return AIMessage(content=message)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[
            [ModelRequest[Any]],
            Awaitable[ModelResponse[Any]],
        ],
    ) -> ModelResponse[Any] | AIMessage:
        """Wrap an asynchronous model call with provider-limit translation.

        Args:
            request: LangChain model request being processed by the agent.
            handler: Next asynchronous model-call handler in the middleware
                chain.

        Returns:
            The awaited model response when the call succeeds, or an
            ``AIMessage`` explaining a recognized provider limit.

        Raises:
            Exception: Re-raises the original exception when it is not a known
                request-size or rate/quota failure.
        """
        try:
            return await handler(request)
        except Exception as error:  # noqa: BLE001
            message = get_model_limit_message(error)
            if message is None:
                raise
            return AIMessage(content=message)
