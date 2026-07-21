"""Application service for ChatOps agent invocations."""

import asyncio
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app.agent.middleware import get_model_limit_message


class AgentInvocationError(RuntimeError):
    """Raised when an agent run cannot produce a usable assistant response."""

    def __init__(
        self,
        message: str,
        *,
        public_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.public_message = public_message


class AgentResponse(BaseModel):
    """Normalized result of one ChatOps agent invocation."""

    content: str
    thread_id: str
    request_id: str


class AgentService:
    """Invoke the ChatOps graph and normalize its response."""

    def __init__(
        self,
        agent: CompiledStateGraph[Any, Any, Any, Any],
        *,
        timeout_seconds: float = 45.0,
    ) -> None:
        self._agent = agent
        self._timeout_seconds = timeout_seconds

    async def invoke(
        self,
        *,
        message: str,
        thread_id: str,
        request_id: str,
    ) -> AgentResponse:
        """Invoke the graph once and return its final text response."""
        normalized_message = message.strip()
        if not normalized_message:
            raise ValueError("message must not be empty")
        if not thread_id.strip():
            raise ValueError("thread_id must not be empty")
        if not request_id.strip():
            raise ValueError("request_id must not be empty")

        config: RunnableConfig = {
            "configurable": {
                "thread_id": thread_id,
                "request_id": request_id,
            },
            "tags": ["chatops"],
            "metadata": {
                "thread_id": thread_id,
                "request_id": request_id,
            },
        }

        try:
            result = await asyncio.wait_for(
                self._agent.ainvoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": normalized_message,
                            }
                        ]
                    },
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as error:
            raise AgentInvocationError(
                "Agent invocation timed out",
                public_message=(
                    "The agent took too long to complete the request. Please try again."
                ),
            ) from error
        except Exception as exc:
            public_message = get_model_limit_message(exc)
            raise AgentInvocationError(
                "Agent graph invocation failed",
                public_message=public_message,
            ) from exc

        messages = result.get("messages") if isinstance(result, dict) else None
        if not messages or not isinstance(messages[-1], AIMessage):
            raise AgentInvocationError("Agent did not return a final assistant message")

        content = messages[-1].text.strip()
        if not content:
            raise AgentInvocationError("Agent returned an empty assistant message")

        return AgentResponse(
            content=content,
            thread_id=thread_id,
            request_id=request_id,
        )
