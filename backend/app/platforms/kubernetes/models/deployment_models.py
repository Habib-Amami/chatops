"""Normalized result models for Kubernetes Deployment operations."""

from typing import Literal

from pydantic import BaseModel, Field


class DeploymentConditionSummary(BaseModel):
    """Small representation of one Kubernetes Deployment condition."""

    type: str
    status: str | None = None
    reason: str | None = None
    message: str | None = None
    last_update: str | None = None


class DeploymentContainerSummary(BaseModel):
    """Container configuration exposed by a Deployment."""

    name: str
    image: str | None = None
    ports: list[int] = Field(default_factory=list)


class DeploymentSummary(BaseModel):
    """Compact Deployment state used by list operations."""

    name: str
    namespace: str
    desired_replicas: int | None = None
    ready_replicas: int | None = None
    available_replicas: int | None = None
    updated_replicas: int | None = None
    paused: bool = False
    labels: dict[str, str] = Field(default_factory=dict)
    conditions: list[DeploymentConditionSummary] = Field(default_factory=list)


class DeploymentDetails(DeploymentSummary):
    """Detailed Deployment metadata, containers, and rollout configuration."""

    annotations: dict[str, str] = Field(default_factory=dict)
    creation_timestamp: str | None = None
    strategy: str | None = None
    containers: list[DeploymentContainerSummary] = Field(default_factory=list)


class DeploymentStatusSummary(BaseModel):
    """Focused rollout-health snapshot for one Deployment."""

    name: str
    namespace: str
    rollout_state: Literal["complete", "in_progress", "degraded", "unknown"]
    desired_replicas: int | None = None
    ready_replicas: int | None = None
    available_replicas: int | None = None
    updated_replicas: int | None = None
    paused: bool = False
    conditions: list[DeploymentConditionSummary] = Field(default_factory=list)


class DeploymentRevisionSummary(BaseModel):
    """One ReplicaSet-backed Deployment revision."""

    revision: int
    replica_set: str | None = None
    images: list[str] = Field(default_factory=list)
    change_cause: str | None = None
    created_at: str | None = None


class DeploymentHistory(BaseModel):
    """Revision history for one Deployment."""

    deployment_name: str
    namespace: str
    revisions: list[DeploymentRevisionSummary] = Field(default_factory=list)


class DeploymentMutationResult(BaseModel):
    """Accepted Deployment mutation without claiming rollout convergence."""

    deployment_name: str
    namespace: str
    operation: Literal[
        "create",
        "delete",
        "scale",
        "restart",
        "update_image",
        "rollback",
        "pause",
        "resume",
    ]
    status: Literal["requested"] = "requested"
    replicas: int | None = None
    container_name: str | None = None
    image: str | None = None
    port: int | None = None
    revision: int | None = None
    message: str


class ServiceSelectorResult(BaseModel):
    """Result of matching a Service selector to Pods."""

    service_name: str
    namespace: str
    status: Literal["ok", "warning", "labels_mismatch"]
    selector: dict[str, str] = Field(default_factory=dict)
    matched_pods: list[str] = Field(default_factory=list)
    running_pods: list[str] = Field(default_factory=list)
    message: str
