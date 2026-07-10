import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent import AgentInvocationError, AgentService


def test_agent_service_invokes_graph_with_run_metadata() -> None:
    agent = MagicMock()
    agent.ainvoke = AsyncMock(
        return_value={"messages": [AIMessage(content="  Pods are healthy.  ")]}
    )
    service = AgentService(agent)

    response = asyncio.run(
        service.invoke(
            message="  Check the pods  ",
            thread_id="thread-1",
            request_id="request-1",
        )
    )

    assert response.model_dump() == {
        "content": "Pods are healthy.",
        "thread_id": "thread-1",
        "request_id": "request-1",
    }
    agent.ainvoke.assert_awaited_once_with(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Check the pods",
                }
            ]
        },
        config={
            "configurable": {"thread_id": "thread-1"},
            "tags": ["chatops"],
            "metadata": {
                "thread_id": "thread-1",
                "request_id": "request-1",
            },
        },
    )


def test_agent_service_rejects_empty_message_before_invocation() -> None:
    agent = MagicMock()
    agent.ainvoke = AsyncMock()
    service = AgentService(agent)

    with pytest.raises(ValueError, match="message"):
        asyncio.run(
            service.invoke(
                message="   ",
                thread_id="thread-1",
                request_id="request-1",
            )
        )

    agent.ainvoke.assert_not_awaited()


def test_agent_service_rejects_missing_final_assistant_message() -> None:
    agent = MagicMock()
    agent.ainvoke = AsyncMock(
        return_value={"messages": [HumanMessage(content="hello")]}
    )
    service = AgentService(agent)

    with pytest.raises(AgentInvocationError, match="final assistant"):
        asyncio.run(
            service.invoke(
                message="hello",
                thread_id="thread-1",
                request_id="request-1",
            )
        )


def test_agent_service_converts_graph_errors_to_invocation_errors() -> None:
    agent = MagicMock()
    agent.ainvoke = AsyncMock(side_effect=RuntimeError("rate limited"))
    service = AgentService(agent)

    with pytest.raises(AgentInvocationError, match="failed"):
        asyncio.run(
            service.invoke(
                message="hello",
                thread_id="thread-1",
                request_id="request-1",
            )
        )


def test_agent_service_times_out_slow_graph_invocation() -> None:
    async def slow_invoke(*args: object, **kwargs: object) -> dict[str, object]:
        await asyncio.sleep(1)
        return {"messages": [AIMessage(content="too late")]}

    agent = MagicMock()
    agent.ainvoke = AsyncMock(side_effect=slow_invoke)
    service = AgentService(agent, timeout_seconds=0.01)

    with pytest.raises(AgentInvocationError, match="timed out"):
        asyncio.run(
            service.invoke(
                message="hello",
                thread_id="thread-1",
                request_id="request-1",
            )
        )
