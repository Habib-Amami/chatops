"""Map Kubernetes Pod SDK objects into stable application models."""

from typing import Literal

from kubernetes import client as kubernetes_client

from app.platforms.kubernetes.models import (
    PodConditionSummary,
    PodContainerStateSummary,
    PodContainerSummary,
    PodDetails,
    PodEventSummary,
    PodLastContainerStateSummary,
    PodOwnerSummary,
    PodStatusDiagnosis,
    PodSummary,
)


def build_pod_summary(
    pod: kubernetes_client.V1Pod,
    namespace: str,
) -> PodSummary | None:
    """Map one Kubernetes SDK Pod into a compact application model.

    Args:
        pod: Kubernetes ``V1Pod`` object returned by the SDK.
        namespace: Requested namespace used when the Pod metadata does not
            contain a namespace.

    Returns:
        A normalized Pod summary, or ``None`` when the SDK object has no Pod
        name and therefore cannot be identified safely.

    Notes:
        A Pod is considered ready only when it declares at least one container
        and every named container has a matching ready container status.
    """
    metadata = pod.metadata
    if metadata is None or metadata.name is None:
        return None

    spec = pod.spec
    status = pod.status
    containers = (
        spec.containers if spec is not None and spec.containers is not None else []
    )
    container_statuses = (
        status.container_statuses
        if status is not None and status.container_statuses is not None
        else []
    )
    statuses_by_name = {
        container_status.name: container_status
        for container_status in container_statuses
        if container_status.name is not None
    }

    return PodSummary(
        name=metadata.name,
        namespace=metadata.namespace or namespace,
        phase=status.phase if status is not None else None,
        ready=bool(containers)
        and all(
            (
                container.name in statuses_by_name
                and statuses_by_name[container.name].ready is True
            )
            for container in containers
            if container.name is not None
        ),
        restart_count=sum(
            container_status.restart_count or 0
            for container_status in container_statuses
        ),
        node_name=spec.node_name if spec is not None else None,
        pod_ip=status.pod_ip if status is not None else None,
        images=[
            container.image for container in containers if container.image is not None
        ],
    )


def build_pod_details(
    pod: kubernetes_client.V1Pod,
    namespace: str,
) -> PodDetails | None:
    """Map one Kubernetes SDK Pod into a detailed application model.

    Args:
        pod: Kubernetes ``V1Pod`` object returned by the SDK.
        namespace: Requested namespace used when Pod metadata omits it.

    Returns:
        Normalized Pod details containing summary data, labels, timestamps,
        containers, conditions, and owners; or ``None`` when the Pod has no
        name.

    Notes:
        Container specifications and runtime statuses are merged by container
        name. Status-only containers are retained so incomplete or changing
        Kubernetes responses do not hide useful diagnostic information.
    """
    summary = build_pod_summary(pod, namespace)
    if summary is None:
        return None

    metadata = pod.metadata
    spec = pod.spec
    status = pod.status
    containers = (spec.containers or []) if spec is not None else []
    init_containers = (
        getattr(spec, "init_containers", None) or [] if spec is not None else []
    )
    container_statuses = (
        status.container_statuses
        if status is not None and status.container_statuses is not None
        else []
    )
    init_container_statuses = (
        getattr(status, "init_container_statuses", None) or []
        if status is not None
        else []
    )
    conditions = (
        status.conditions
        if status is not None and status.conditions is not None
        else []
    )

    return PodDetails(
        **summary.model_dump(),
        labels=dict(metadata.labels or {}) if metadata is not None else {},
        created_at=serialize_timestamp(
            metadata.creation_timestamp if metadata is not None else None
        ),
        containers=_build_container_summaries(containers, container_statuses),
        init_containers=_build_container_summaries(
            init_containers,
            init_container_statuses,
        ),
        conditions=[
            PodConditionSummary(
                type=condition.type,
                status=condition.status,
                reason=condition.reason,
                message=condition.message,
            )
            for condition in conditions
            if condition.type is not None
        ],
        owners=[
            PodOwnerSummary(
                kind=owner.kind,
                name=owner.name,
                uid=str(owner.uid) if owner.uid is not None else None,
                controller=owner.controller is True,
            )
            for owner in getattr(metadata, "owner_references", None) or []
            if owner.kind is not None and owner.name is not None
        ],
    )


def build_pod_events(
    events: list[kubernetes_client.CoreV1Event],
    limit: int,
) -> list[PodEventSummary]:
    """Map Kubernetes Pod events into a bounded, newest-first model list.

    Args:
        events: Kubernetes ``CoreV1Event`` objects associated with a Pod.
        limit: Maximum number of the newest events to include.

    Returns:
        Normalized event summaries ordered from newest to oldest.

    Notes:
        Event count and timestamps use Kubernetes' newer event-series fields
        as fallbacks when the legacy event fields are absent.
    """
    newest_events = sorted(events, key=_event_sort_key, reverse=True)[:limit]
    return [
        PodEventSummary(
            type=event.type,
            reason=event.reason,
            message=event.message,
            count=(
                event.count
                if event.count is not None
                else getattr(getattr(event, "series", None), "count", None)
            ),
            first_timestamp=serialize_timestamp(
                event.first_timestamp
                or getattr(
                    getattr(event, "metadata", None),
                    "creation_timestamp",
                    None,
                )
            ),
            last_timestamp=serialize_timestamp(_event_observed_at(event)),
        )
        for event in newest_events
    ]


def build_pod_status_diagnosis(
    pod: kubernetes_client.V1Pod,
    namespace: str,
    pod_name: str,
) -> PodStatusDiagnosis:
    """Map Kubernetes Pod status into a container-level diagnosis model.

    Args:
        pod: Kubernetes ``V1Pod`` whose runtime state should be diagnosed.
        namespace: Namespace used to identify the diagnosed Pod.
        pod_name: Exact name used to identify the diagnosed Pod.

    Returns:
        A normalized diagnosis containing the Pod phase, reason, message, and
        runtime states for init, regular, and ephemeral containers.

    Notes:
        Missing Pod phases are represented as ``"Unknown"``. When Kubernetes
        provides neither a message nor container statuses, the result includes
        a message explaining that status information is not available yet.
    """
    status = pod.status
    container_statuses = (
        status.container_statuses
        if status is not None and status.container_statuses is not None
        else []
    )
    init_container_statuses = (
        getattr(status, "init_container_statuses", None) or []
        if status is not None
        else []
    )
    ephemeral_container_statuses = (
        getattr(status, "ephemeral_container_statuses", None) or []
        if status is not None
        else []
    )
    containers = [
        *(
            _build_container_state(container_status, container_type="init")
            for container_status in init_container_statuses
            if container_status.name is not None
        ),
        *(
            _build_container_state(container_status)
            for container_status in container_statuses
            if container_status.name is not None
        ),
        *(
            _build_container_state(container_status, container_type="ephemeral")
            for container_status in ephemeral_container_statuses
            if container_status.name is not None
        ),
    ]
    status_reason = getattr(status, "reason", None) if status else None
    status_message = getattr(status, "message", None) if status else None

    return PodStatusDiagnosis(
        pod_name=pod_name,
        namespace=namespace,
        phase=status.phase if status is not None and status.phase else "Unknown",
        containers=containers,
        reason=status_reason,
        message=status_message
        or (
            None if containers else "No container status information is available yet."
        ),
    )


def _build_container_summaries(
    containers: list[kubernetes_client.V1Container],
    container_statuses: list[kubernetes_client.V1ContainerStatus],
) -> list[PodContainerSummary]:
    """Merge container specifications and runtime statuses by name.

    Args:
        containers: Container specifications declared on the Pod.
        container_statuses: Runtime statuses reported by Kubernetes.

    Returns:
        Container summaries in specification order, followed by any runtime
        statuses that have no matching container specification.
    """
    statuses_by_name = {
        status.name: status for status in container_statuses if status.name is not None
    }
    summaries: list[PodContainerSummary] = []
    seen_names: set[str] = set()

    for container in containers:
        name = getattr(container, "name", None)
        if name is None:
            continue
        status = statuses_by_name.get(name)
        summaries.append(
            PodContainerSummary(
                name=name,
                image=container.image,
                ready=status is not None and status.ready is True,
                restart_count=status.restart_count or 0 if status is not None else 0,
            )
        )
        seen_names.add(name)

    for status in container_statuses:
        if status.name is None or status.name in seen_names:
            continue
        summaries.append(
            PodContainerSummary(
                name=status.name,
                image=status.image,
                ready=status.ready is True,
                restart_count=status.restart_count or 0,
            )
        )
    return summaries


def _build_container_state(
    container_status: kubernetes_client.V1ContainerStatus,
    *,
    container_type: Literal["container", "init", "ephemeral"] = "container",
) -> PodContainerStateSummary:
    """Map one container status into a normalized diagnostic state.

    Args:
        container_status: Runtime status reported for one container.
        container_type: Kubernetes category of the container.

    Returns:
        Current and previous runtime state details for the container. An
        unreported current state is represented as ``"Unknown"``.
    """
    current_state = _build_runtime_state(container_status.state)
    if current_state is None:
        current_state = PodLastContainerStateSummary(state="Unknown")

    return PodContainerStateSummary(
        **current_state.model_dump(),
        name=container_status.name or "unknown",
        container_type=container_type,
        ready=container_status.ready is True,
        restart_count=container_status.restart_count or 0,
        last_state=_build_runtime_state(getattr(container_status, "last_state", None)),
    )


def _build_runtime_state(
    state: kubernetes_client.V1ContainerState | None,
) -> PodLastContainerStateSummary | None:
    """Normalize a Kubernetes running, terminated, or waiting state.

    Args:
        state: Kubernetes container state object, or ``None`` when unavailable.

    Returns:
        A normalized runtime-state model, or ``None`` when Kubernetes provides
        no recognized state information.
    """
    if state is None:
        return None

    running = getattr(state, "running", None)
    if running is not None:
        return PodLastContainerStateSummary(
            state="Running",
            started_at=serialize_timestamp(running.started_at),
        )

    terminated = getattr(state, "terminated", None)
    if terminated is not None:
        return PodLastContainerStateSummary(
            state="Terminated",
            reason=terminated.reason,
            message=terminated.message,
            exit_code=terminated.exit_code,
            signal=terminated.signal,
            started_at=serialize_timestamp(terminated.started_at),
            finished_at=serialize_timestamp(terminated.finished_at),
        )

    waiting = getattr(state, "waiting", None)
    if waiting is not None:
        return PodLastContainerStateSummary(
            state="Waiting",
            reason=waiting.reason,
            message=waiting.message,
        )
    return None


def _event_observed_at(event: kubernetes_client.CoreV1Event) -> object | None:
    """Select the best available observation timestamp for an event.

    Args:
        event: Kubernetes event whose timestamp should be resolved.

    Returns:
        The most relevant available timestamp, preferring the latest legacy or
        event-series observation fields, or ``None`` when none are present.
    """
    series = getattr(event, "series", None)
    metadata = getattr(event, "metadata", None)
    return (
        event.last_timestamp
        or getattr(series, "last_observed_time", None)
        or getattr(event, "event_time", None)
        or event.first_timestamp
        or getattr(metadata, "creation_timestamp", None)
    )


def _event_sort_key(event: kubernetes_client.CoreV1Event) -> str:
    """Build a stable timestamp string used to sort Pod events.

    Args:
        event: Kubernetes event to order.

    Returns:
        An ISO-like timestamp string, or an empty string when no timestamp is
        available.
    """
    return serialize_timestamp(_event_observed_at(event)) or ""


def serialize_timestamp(value: object | None) -> str | None:
    """Convert a Kubernetes timestamp-like value into a stable string.

    Args:
        value: Datetime-like or scalar timestamp value returned by Kubernetes.

    Returns:
        The result of ``isoformat()`` when available, otherwise ``str(value)``;
        or ``None`` when no value was provided.
    """
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else str(value)
