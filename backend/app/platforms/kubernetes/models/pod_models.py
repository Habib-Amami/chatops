"""Normalized result models for Kubernetes Pod operations."""

from typing import Literal

from pydantic import BaseModel, Field


class PodSummary(BaseModel):
    """Small, agent-safe representation of a Kubernetes Pod."""

    name: str
    namespace: str
    phase: str | None
    ready: bool
    restart_count: int
    node_name: str | None
    pod_ip: str | None
    images: list[str]


class PodContainerSummary(BaseModel):
    """Small, agent-safe representation of one Pod container."""

    name: str
    image: str | None
    ready: bool
    restart_count: int


class PodOwnerSummary(BaseModel):
    """One Kubernetes owner reference attached to a Pod."""

    kind: str
    name: str
    uid: str | None
    controller: bool


class PodConditionSummary(BaseModel):
    """Small, agent-safe representation of one Pod condition."""

    type: str
    status: str | None
    reason: str | None
    message: str | None


class PodDetails(PodSummary):
    """Detailed, read-only Pod information for diagnosis."""

    labels: dict[str, str]
    created_at: str | None
    containers: list[PodContainerSummary]
    init_containers: list[PodContainerSummary] = Field(default_factory=list)
    conditions: list[PodConditionSummary]
    owners: list[PodOwnerSummary] = Field(default_factory=list)


class PodEventSummary(BaseModel):
    """Small, agent-safe representation of one Kubernetes event."""

    type: str | None
    reason: str | None
    message: str | None
    count: int | None
    first_timestamp: str | None
    last_timestamp: str | None


class PodLastContainerStateSummary(BaseModel):
    """Previous runtime state reported for one Pod container."""

    state: str
    reason: str | None = None
    message: str | None = None
    exit_code: int | None = None
    signal: int | None = None
    started_at: str | None = None
    finished_at: str | None = None


class PodContainerStateSummary(PodLastContainerStateSummary):
    """Current and previous runtime state for one Pod container."""

    name: str
    container_type: Literal["container", "init", "ephemeral"] = "container"
    ready: bool
    restart_count: int
    last_state: PodLastContainerStateSummary | None = None


class PodStatusDiagnosis(BaseModel):
    """Container-level Pod status used when logs are unavailable."""

    pod_name: str
    namespace: str
    phase: str
    containers: list[PodContainerStateSummary]
    reason: str | None = None
    message: str | None = None


class PodDeleteResult(BaseModel):
    """Deletion acceptance and bounded Kubernetes verification result."""

    pod_name: str
    namespace: str
    status: Literal["deleted", "deletion_timeout", "verification_error"]
    deleted: bool
    verification_message: str | None = None


class PodCreateResult(BaseModel):
    """Creation acceptance and bounded Kubernetes verification result."""

    pod_name: str
    namespace: str
    image: str
    registry: str
    manifest_verified: bool = True
    status: Literal[
        "ready",
        "succeeded",
        "failed",
        "readiness_timeout",
        "verification_error",
    ]
    phase: str | None = None
    ready: bool = False
    verification_message: str | None = None
