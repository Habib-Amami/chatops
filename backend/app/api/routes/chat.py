"""ChatOps agent HTTP endpoint."""

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.agent import AgentInvocationError, AgentService
from app.api.dependencies import get_agent_service
from app.api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> ChatResponse:
    """Send one message to the ChatOps agent."""
    thread_id = request.thread_id or uuid4()
    request_id = uuid4()

    try:
        response = await agent_service.invoke(
            message=request.message,
            thread_id=str(thread_id),
            request_id=str(request_id),
        )
        return ChatResponse.model_validate(response.model_dump())
    except AgentInvocationError as error:
        # Return a friendly chat message instead of crashing the connection.
        # This prevents "Connection error: Failed to fetch" in the frontend.
        logger.error(
            "Agent invocation failed",
            extra={
                "thread_id": str(thread_id),
                "request_id": str(request_id),
            },
            exc_info=True,
        )
        error_str = str(error)
        if "rate_limit" in error_str or "429" in error_str:
            msg = (
                "⚠️ The AI model is temporarily rate-limited. "
                "Please wait a moment and try again."
            )
        elif "413" in error_str or "too large" in error_str.lower():
            msg = (
                "⚠️ Your request is too long for the current model. "
                "Please start a new chat session and try a shorter command."
            )
        else:
            msg = f"⚠️ The agent encountered an error: {error}"
        return ChatResponse(
            content=msg,
            thread_id=str(thread_id),
            request_id=str(request_id),
        )
