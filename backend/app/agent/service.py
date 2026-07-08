"""Application service for ChatOps agent invocations."""

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

class AgentInvocationError(RuntimeError):
    """Raised when an agent run does not produce a usable assistant response."""


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
    ) -> None:
        self._agent = agent

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
            "configurable": {"thread_id": thread_id},
            "tags": ["chatops"],
            "metadata": {
                "thread_id": thread_id,
                "request_id": request_id,
            },
        }

        result = await self._agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": normalized_message,
                    }
                ]
            },
            config=config,
        )

        messages = result.get("messages") if isinstance(result, dict) else None
        if not messages or not isinstance(messages[-1], AIMessage):
            raise AgentInvocationError(
                "Agent did not return a final assistant message"
            )

        content = messages[-1].text.strip()
        if not content:
            raise AgentInvocationError("Agent returned an empty assistant message")

        return AgentResponse(
            content=content,
            thread_id=thread_id,
            request_id=request_id,
        )
