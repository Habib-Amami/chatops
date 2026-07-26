"""Agent-facing formatting for Kubernetes Deployment tool observations."""

from app.platforms.kubernetes.models import (
    DeploymentConditionSummary,
    DeploymentDetails,
    DeploymentHistory,
    DeploymentMutationResult,
    DeploymentStatusSummary,
    DeploymentSummary,
    ServiceSelectorResult,
)


def format_deployment_list(
    deployments: list[DeploymentSummary],
    namespace: str,
) -> str:
    """Format a bounded Deployment summary list."""
    if not deployments:
        return f"No Deployments found in namespace {namespace!r}."

    lines = [f"Deployments in namespace {namespace!r}:"]
    for deployment in deployments:
        lines.append(
            f"- {deployment.name}: desired={_value(deployment.desired_replicas)}, "
            f"ready={_value(deployment.ready_replicas)}, "
            f"available={_value(deployment.available_replicas)}, "
            f"updated={_value(deployment.updated_replicas)}, "
            f"paused={_yes_no(deployment.paused)}"
        )
    return "\n".join(lines)


def format_deployment_details(deployment: DeploymentDetails) -> str:
    """Format detailed Deployment state without exposing raw SDK objects."""
    lines = [
        f"Deployment {deployment.name!r} in namespace {deployment.namespace!r}:",
        (
            "Replicas: "
            f"desired={_value(deployment.desired_replicas)}, "
            f"ready={_value(deployment.ready_replicas)}, "
            f"available={_value(deployment.available_replicas)}, "
            f"updated={_value(deployment.updated_replicas)}"
        ),
        f"Paused: {_yes_no(deployment.paused)}",
        f"Strategy: {deployment.strategy or 'unknown'}",
    ]
    if deployment.creation_timestamp:
        lines.append(f"Created: {deployment.creation_timestamp}")
    if deployment.labels:
        lines.append(f"Labels: {_mapping(deployment.labels)}")
    if deployment.containers:
        lines.append("Containers:")
        for container in deployment.containers:
            ports = ",".join(str(port) for port in container.ports) or "none"
            lines.append(
                f"- {container.name}: image={container.image or 'unknown'}, "
                f"ports={ports}"
            )
    lines.extend(_condition_lines(deployment.conditions))
    return "\n".join(lines)


def format_deployment_status(status: DeploymentStatusSummary) -> str:
    """Format focused Deployment rollout health."""
    lines = [
        f"Deployment {status.name!r} rollout in namespace {status.namespace!r}:",
        f"State: {status.rollout_state}",
        (
            "Replicas: "
            f"desired={_value(status.desired_replicas)}, "
            f"ready={_value(status.ready_replicas)}, "
            f"available={_value(status.available_replicas)}, "
            f"updated={_value(status.updated_replicas)}"
        ),
        f"Paused: {_yes_no(status.paused)}",
    ]
    lines.extend(_condition_lines(status.conditions))
    return "\n".join(lines)


def format_deployment_history(history: DeploymentHistory) -> str:
    """Format Deployment revisions in ascending order."""
    if not history.revisions:
        return (
            f"No revisions found for Deployment {history.deployment_name!r} "
            f"in namespace {history.namespace!r}."
        )

    lines = [
        f"Revision history for Deployment {history.deployment_name!r} "
        f"in namespace {history.namespace!r}:"
    ]
    for revision in history.revisions:
        images = ", ".join(revision.images) or "unknown"
        replica_set = revision.replica_set or "unknown"
        change_cause = revision.change_cause or "<none>"
        created_at = revision.created_at or "unknown"
        lines.append(
            f"- revision={revision.revision}, replica_set={replica_set}, "
            f"images={images}, change_cause={change_cause}, created={created_at}"
        )
    return "\n".join(lines)


def format_deployment_mutation(result: DeploymentMutationResult) -> str:
    """Format one accepted Deployment mutation request."""
    details: list[str] = []
    if result.replicas is not None:
        details.append(f"replicas={result.replicas}")
    if result.container_name:
        details.append(f"container={result.container_name}")
    if result.image:
        details.append(f"image={result.image}")
    if result.port is not None:
        details.append(f"port={result.port}")
    if result.revision is not None:
        details.append(f"revision={result.revision}")
    detail_text = f" ({', '.join(details)})" if details else ""
    return (
        f"Kubernetes accepted the {result.operation} request for Deployment "
        f"{result.deployment_name!r} in namespace {result.namespace!r}"
        f"{detail_text}. {result.message}"
    )


def format_service_selector(result: ServiceSelectorResult) -> str:
    """Format Service selector matching results."""
    selector = _mapping(result.selector) if result.selector else "none"
    matched = ", ".join(result.matched_pods) or "none"
    running = ", ".join(result.running_pods) or "none"
    return (
        f"Service {result.service_name!r} selector check in namespace "
        f"{result.namespace!r}: status={result.status}, selector={selector}, "
        f"matched_pods={matched}, running_pods={running}. {result.message}"
    )


def _condition_lines(
    conditions: list[DeploymentConditionSummary],
) -> list[str]:
    if not conditions:
        return ["Conditions: none reported"]
    lines = ["Conditions:"]
    for condition in conditions:
        details = [
            f"status={condition.status or 'unknown'}",
            f"reason={condition.reason or 'none'}",
        ]
        if condition.message:
            details.append(f"message={condition.message}")
        lines.append(f"- {condition.type}: {', '.join(details)}")
    return lines


def _mapping(values: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(values.items()))


def _value(value: int | None) -> str:
    return str(value) if value is not None else "unknown"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
