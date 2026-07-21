"""Normalized result models for AWS EC2 operations."""

from pydantic import BaseModel


class EC2InstanceSummary(BaseModel):
    """Small, agent-safe representation of an EC2 instance."""

    instance_id: str
    instance_type: str
    state: str
    private_ip: str | None
    public_ip: str | None
    launch_time: str | None
