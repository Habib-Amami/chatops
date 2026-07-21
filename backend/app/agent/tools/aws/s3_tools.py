"""Agent tools backed by the S3 service."""

from langchain.tools import BaseTool, tool

from app.agent.tools.aws.formatters import format_s3_buckets, format_s3_objects
from app.platforms.aws.services import S3Service


def create_s3_tools(s3_service: S3Service) -> list[BaseTool]:
    """Create S3 tools bound to an initialized service."""

    @tool
    def list_s3_buckets() -> str:
        """List all accessible S3 buckets on LocalStack.

        Use this when a user asks which S3 buckets exist,
        what storage is available, or to inspect the AWS environment.
        """
        buckets = s3_service.list_buckets()
        return format_s3_buckets(buckets)

    @tool
    def list_s3_objects(bucket: str, prefix: str = "") -> str:
        """List objects stored in an allowed S3 bucket.

        Use this when a user asks what files or logs are stored in S3,
        wants to inspect audit logs, or needs to find a specific object.

        Args:
            bucket: The name of the S3 bucket to inspect.
            prefix: Optional key prefix to filter results.
        """
        objects = s3_service.list_objects(bucket, prefix)
        return format_s3_objects(objects, bucket, prefix)

    return [list_s3_buckets, list_s3_objects]
