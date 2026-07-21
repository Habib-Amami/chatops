"""Centralized agent-facing text formatting for EC2 tools."""

from app.platforms.aws.models import EC2InstanceSummary


def format_ec2_instances(
    instances: list[EC2InstanceSummary],
    state_filter: str | None = None,
) -> str:
    """Format EC2 instance summaries as a provider-safe tool observation.

    Args:
        instances: Structured EC2 instance summaries returned by the service.
        state_filter: Optional instance-state filter used for the request.

    Returns:
        A concise string describing the matching instances or the empty result.
    """
    if not instances:
        if state_filter:
            return f"No EC2 instances were found with state {state_filter!r}."
        return "No EC2 instances were found."

    rows = "\n".join(
        "- "
        f"{instance.instance_id}: state={instance.state}, "
        f"type={instance.instance_type}, "
        f"private_ip={instance.private_ip or 'none'}, "
        f"public_ip={instance.public_ip or 'none'}, "
        f"launched_at={instance.launch_time or 'unknown'}"
        for instance in instances
    )
    heading = (
        f"EC2 instances with state {state_filter!r}:"
        if state_filter
        else "EC2 instances:"
    )
    return f"{heading}\n{rows}"
