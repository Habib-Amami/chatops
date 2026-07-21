"""Normalized result models for AWS S3 operations."""

from pydantic import BaseModel


class BucketSummary(BaseModel):
    """Small, agent-safe representation of an S3 bucket."""

    name: str
    creation_date: str | None


class ObjectSummary(BaseModel):
    """Small, agent-safe representation of an S3 object."""

    key: str
    size: int
    last_modified: str | None
    bucket: str
