"""ChatOps agent HTTP endpoint."""

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.agent import AgentInvocationError, AgentService
from app.api.dependencies import get_agent_service
from app.api.schemas import ChatRequest, ChatResponse

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
    except AgentInvocationError as error:
        logger.warning(
            "Agent invocation failed",
            extra={
                "thread_id": str(thread_id),
                "request_id": str(request_id),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The agent request failed or timed out",
        ) from error

    return ChatResponse.model_validate(response.model_dump())
