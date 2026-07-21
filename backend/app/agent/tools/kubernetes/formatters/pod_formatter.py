"""Centralized agent-facing text formatting for Kubernetes Pod tools."""

from langchain_core.tools import ToolException

from app.platforms.kubernetes.models import (
    PodContainerSummary,
    PodContainerStateSummary,
    PodCreateResult,
    PodDeleteResult,
    PodDetails,
    PodEventSummary,
    PodLastContainerStateSummary,
    PodStatusDiagnosis,
    PodSummary,
)

MAX_LOG_CHARACTERS = 3_000
LOG_TRUNCATION_MARKER = (
    "[... older log output truncated to protect the conversation context ...]"
)
INVALID_TOOL_INPUT_MESSAGE = (
    "Kubernetes operation could not run because required parameters were "
    "missing or invalid. Do not retry until every required resource name and "
    "namespace is known."
)


def format_tool_error(error: ToolException) -> str:
    """Return a compact error observation the model can safely report."""
    return f"Kubernetes operation failed: {error}"


def format_pod_list(pods: list[PodSummary], namespace: str) -> str:
    """Format a namespace-scoped Pod list."""
    if not pods:
        return f"No pods were found in namespace {namespace!r}."

    rows = "\n".join(
        "- "
        f"{pod.name}: {pod.phase or 'unknown phase'}, "
        f"{'ready' if pod.ready else 'not ready'}, "
        f"restarts={pod.restart_count}, node={pod.node_name or 'unknown node'}, "
        f"ip={pod.pod_ip or 'unknown IP'}, "
        f"images={', '.join(pod.images) if pod.images else 'unknown image'}"
        for pod in pods
    )
    return f"Pods in namespace {namespace!r}:\n{rows}"


def format_pod_details(pod: PodDetails) -> str:
    """Format detailed status for one Pod."""
    labels = (
        ", ".join(f"{key}={value}" for key, value in sorted(pod.labels.items()))
        if pod.labels
        else "none"
    )
    owners = (
        ", ".join(
            f"{owner.kind}/{owner.name}" + (" (controller)" if owner.controller else "")
            for owner in pod.owners
        )
        if pod.owners
        else "none"
    )
    containers = _format_container_summaries(
        pod.containers,
        empty_message="- no container statuses reported",
    )
    init_containers = _format_container_summaries(
        pod.init_containers,
        empty_message="- none",
    )
    conditions = (
        "\n".join(
            "- "
            f"{condition.type}: status={condition.status or 'unknown'}, "
            f"reason={condition.reason or 'none'}, "
            f"message={condition.message or 'none'}"
            for condition in pod.conditions
        )
        if pod.conditions
        else "- no conditions reported"
    )

    return (
        f"Pod {pod.name!r} in namespace {pod.namespace!r}:\n"
        f"Phase: {pod.phase or 'unknown'}\n"
        f"Ready: {'yes' if pod.ready else 'no'}\n"
        f"Restarts: {pod.restart_count}\n"
        f"Node: {pod.node_name or 'unknown'}\n"
        f"IP: {pod.pod_ip or 'unknown'}\n"
        f"Created at: {pod.created_at or 'unknown'}\n"
        f"Labels: {labels}\n"
        f"Owners: {owners}\n"
        f"Containers:\n{containers}\n"
        f"Init containers:\n{init_containers}\n"
        f"Conditions:\n{conditions}"
    )


def format_pod_logs(
    logs: str,
    pod_name: str,
    namespace: str,
    *,
    previous: bool,
) -> str:
    """Format and context-bound raw logs for an agent observation."""
    log_kind = "Previous" if previous else "Recent"
    bounded_logs = _truncate_logs(logs)
    if not bounded_logs:
        return (
            f"No {log_kind.lower()} logs were returned for pod {pod_name!r} "
            f"in namespace {namespace!r}."
        )
    return (
        f"{log_kind} logs for pod {pod_name!r} "
        f"in namespace {namespace!r}:\n{bounded_logs}"
    )


def format_pod_events(
    events: list[PodEventSummary],
    pod_name: str,
    namespace: str,
) -> str:
    """Format Pod events as one consistent observation."""
    if not events:
        return f"No events were found for pod {pod_name!r} in namespace {namespace!r}."
    return f"Events for pod {pod_name!r} in namespace {namespace!r}:\n" + "\n".join(
        _format_event(event) for event in events
    )


def format_pod_diagnosis(diagnosis: PodStatusDiagnosis) -> str:
    """Format current and previous container states for one Pod."""
    containers = (
        "\n".join(
            _format_container_state(container) for container in diagnosis.containers
        )
        if diagnosis.containers
        else "- no container status information reported"
    )
    return (
        f"Status diagnosis for pod {diagnosis.pod_name!r} "
        f"in namespace {diagnosis.namespace!r}:\n"
        f"Phase: {diagnosis.phase}\n"
        f"Reason: {diagnosis.reason or 'none'}\n"
        f"Message: {diagnosis.message or 'none'}\n"
        f"Containers:\n{containers}"
    )


def format_pod_create_result(result: PodCreateResult) -> str:
    """Format accepted creation together with bounded readiness verification."""
    verification_message = (
        f", verification_message={result.verification_message}"
        if result.verification_message
        else ""
    )
    return (
        f"Kubernetes accepted standalone pod {result.pod_name!r} in namespace "
        f"{result.namespace!r}: image={result.image}, registry={result.registry}, "
        f"manifest_verified={'yes' if result.manifest_verified else 'no'}, "
        f"verification_status={result.status}, phase={result.phase or 'unknown'}, "
        f"ready={'yes' if result.ready else 'no'}{verification_message}."
    )


def format_pod_delete_result(result: PodDeleteResult) -> str:
    """Format accepted deletion together with bounded absence verification."""
    verification_message = (
        f", verification_message={result.verification_message}"
        if result.verification_message
        else ""
    )
    return (
        f"Kubernetes accepted deletion of pod {result.pod_name!r} in namespace "
        f"{result.namespace!r}: verification_status={result.status}, "
        f"deleted={'yes' if result.deleted else 'no'}{verification_message}."
    )


def format_pod_description(
    pod: PodDetails,
    events: list[PodEventSummary],
) -> str:
    """Format details and events as one describe-style observation."""
    formatted_events = (
        "\n".join(_format_event(event) for event in events)
        if events
        else "- no events reported"
    )
    return f"{format_pod_details(pod)}\nEvents:\n{formatted_events}"


def _format_container_summaries(
    containers: list[PodContainerSummary],
    *,
    empty_message: str,
) -> str:
    if not containers:
        return empty_message
    return "\n".join(
        "- "
        f"{container.name}: image={container.image or 'unknown image'}, "
        f"{'ready' if container.ready else 'not ready'}, "
        f"restarts={container.restart_count}"
        for container in containers
    )


def _format_event(event: PodEventSummary) -> str:
    return (
        f"- {event.type or 'Unknown'} {event.reason or 'Unknown'}: "
        f"{event.message or 'No message'} "
        f"(count={event.count if event.count is not None else 'unknown'}, "
        f"last_seen={event.last_timestamp or 'unknown'})"
    )


def _format_container_state(container: PodContainerStateSummary) -> str:
    details = _format_runtime_state(container)
    last_state = (
        _format_runtime_state(container.last_state)
        if container.last_state is not None
        else "none"
    )
    return (
        f"- {container.container_type}/{container.name}: {details}, "
        f"{'ready' if container.ready else 'not ready'}, "
        f"restarts={container.restart_count}, last_state={last_state}"
    )


def _format_runtime_state(state: PodLastContainerStateSummary) -> str:
    details = [state.state]
    if state.reason:
        details.append(f"reason={state.reason}")
    if state.message:
        details.append(f"message={state.message}")
    if state.exit_code is not None:
        details.append(f"exit_code={state.exit_code}")
    if state.signal is not None:
        details.append(f"signal={state.signal}")
    if state.started_at:
        details.append(f"started_at={state.started_at}")
    if state.finished_at:
        details.append(f"finished_at={state.finished_at}")
    return ", ".join(details)


def _truncate_logs(logs: str) -> str:
    if len(logs) <= MAX_LOG_CHARACTERS:
        return logs

    prefix = f"{LOG_TRUNCATION_MARKER}\n"
    available_characters = max(MAX_LOG_CHARACTERS - len(prefix), 1)
    recent_logs = logs[-available_characters:]
    first_newline = recent_logs.find("\n")
    if first_newline != -1 and first_newline < len(recent_logs) - 1:
        recent_logs = recent_logs[first_newline + 1 :]
    return f"{prefix}{recent_logs}"
