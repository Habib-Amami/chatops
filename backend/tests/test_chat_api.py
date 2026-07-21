from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent import AgentInvocationError, AgentResponse
from app.api.dependencies import get_agent_service
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_endpoint_invokes_agent_service() -> None:
    thread_id = uuid4()
    agent_service = MagicMock()
    agent_service.invoke = AsyncMock(
        return_value=AgentResponse(
            content="The pods are healthy.",
            thread_id=str(thread_id),
            request_id=str(uuid4()),
        )
    )

    async def override_agent_service() -> MagicMock:
        return agent_service

    app.dependency_overrides[get_agent_service] = override_agent_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "message": "  Check the pods  ",
                    "thread_id": str(thread_id),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "The pods are healthy."
    assert body["thread_id"] == str(thread_id)
    UUID(body["request_id"])
    invocation = agent_service.invoke.await_args.kwargs
    assert invocation["message"] == "Check the pods"
    assert invocation["thread_id"] == str(thread_id)
    UUID(invocation["request_id"])


@pytest.mark.anyio
async def test_chat_endpoint_generates_thread_id() -> None:
    agent_service = MagicMock()

    async def invoke(**kwargs: str) -> AgentResponse:
        return AgentResponse(content="No pods found.", **kwargs)

    agent_service.invoke = AsyncMock(side_effect=invoke)

    async def override_agent_service() -> MagicMock:
        return agent_service

    app.dependency_overrides[get_agent_service] = override_agent_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={"message": "List pods"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    UUID(response.json()["thread_id"])


@pytest.mark.anyio
async def test_chat_endpoint_rejects_whitespace_only_message() -> None:
    agent_service = MagicMock()
    agent_service.invoke = AsyncMock()

    async def override_agent_service() -> MagicMock:
        return agent_service

    app.dependency_overrides[get_agent_service] = override_agent_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/chat",
                json={"message": "   "},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    agent_service.invoke.assert_not_awaited()


@pytest.mark.anyio
async def test_chat_endpoint_does_not_expose_internal_agent_errors() -> None:
    agent_service = MagicMock()
    agent_service.invoke = AsyncMock(
        side_effect=AgentInvocationError(
            "provider request failed with secret-token-value"
        )
    )

    async def override_agent_service() -> MagicMock:
        return agent_service

    app.dependency_overrides[get_agent_service] = override_agent_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat",
                json={"message": "List pods"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["content"] == (
        "The agent could not complete the request. Please try again."
    )
    assert "secret-token-value" not in response.text


@pytest.mark.anyio
async def test_chat_endpoint_returns_only_explicit_safe_error_message() -> None:
    agent_service = MagicMock()
    agent_service.invoke = AsyncMock(
        side_effect=AgentInvocationError(
            "internal timeout details",
            public_message="The agent took too long. Please try again.",
        )
    )

    async def override_agent_service() -> MagicMock:
        return agent_service

    app.dependency_overrides[get_agent_service] = override_agent_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat",
                json={"message": "List pods"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["content"] == ("The agent took too long. Please try again.")
    assert "internal timeout details" not in response.text
