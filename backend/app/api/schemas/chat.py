"""Schemas for the chat endpoint."""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """One user message and an optional existing conversation identifier."""

    message: str = Field(min_length=1, max_length=10_000)
    thread_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        """Reject whitespace-only messages and normalize surrounding whitespace."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized


class ChatResponse(BaseModel):
    """Final assistant response with correlation identifiers."""

    content: str
    thread_id: UUID
    request_id: UUID
