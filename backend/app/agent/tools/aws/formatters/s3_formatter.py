"""Centralized agent-facing text formatting for S3 tools."""

from app.platforms.aws.models import BucketSummary, ObjectSummary


def format_s3_buckets(buckets: list[BucketSummary]) -> str:
    """Format S3 bucket summaries as a provider-safe tool observation.

    Args:
        buckets: Structured bucket summaries returned by the S3 service.

    Returns:
        A concise string describing the buckets or the empty result.
    """
    if not buckets:
        return "No S3 buckets were found."

    rows = "\n".join(
        f"- {bucket.name}: created_at={bucket.creation_date or 'unknown'}"
        for bucket in buckets
    )
    return f"S3 buckets:\n{rows}"


def format_s3_objects(
    objects: list[ObjectSummary],
    bucket: str,
    prefix: str = "",
) -> str:
    """Format S3 object summaries as a provider-safe tool observation.

    Args:
        objects: Structured object summaries returned by the S3 service.
        bucket: Bucket inspected by the tool.
        prefix: Optional key prefix used to filter the request.

    Returns:
        A concise string describing the objects or the empty result.
    """
    scope = f"bucket {bucket!r}"
    if prefix:
        scope += f" with prefix {prefix!r}"

    if not objects:
        return f"No S3 objects were found in {scope}."

    rows = "\n".join(
        "- "
        f"{item.key}: size_bytes={item.size}, "
        f"last_modified={item.last_modified or 'unknown'}"
        for item in objects
    )
    return f"S3 objects in {scope}:\n{rows}"
