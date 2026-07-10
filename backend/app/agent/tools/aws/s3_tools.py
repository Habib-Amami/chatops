"""Agent tools backed by the S3 service."""

from langchain.tools import BaseTool, tool

from app.platforms.aws.services import S3Service


def create_s3_tools(s3_service: S3Service) -> list[BaseTool]:
    """Create S3 tools bound to an initialized service."""

    @tool
    def list_s3_buckets() -> list[dict[str, object]]:
        """List all accessible S3 buckets on LocalStack.

        Use this when a user asks which S3 buckets exist,
        what storage is available, or to inspect the AWS environment.
        """
        buckets = s3_service.list_buckets()
        return [bucket.model_dump(mode="json") for bucket in buckets]

    @tool
    def list_s3_objects(bucket: str, prefix: str = "") -> list[dict[str, object]]:
        """List objects stored in an allowed S3 bucket.

        Use this when a user asks what files or logs are stored in S3,
        wants to inspect audit logs, or needs to find a specific object.

        Args:
            bucket: The name of the S3 bucket to inspect.
            prefix: Optional key prefix to filter results.
        """
        objects = s3_service.list_objects(bucket, prefix)
        return [obj.model_dump(mode="json") for obj in objects]

    @tool
    def save_audit_log(action: str, target: str, result: str) -> dict[str, object]:
        """Save a ChatOps audit entry to S3.

        Use this after executing any important action to keep a record.

        Args:
            action: The action performed (e.g. restart, scale, fault).
            target: The target resource (e.g. backend, frontend).
            result: The outcome of the action.
        """
        uploaded = s3_service.save_audit_log(action, target, result)
        return uploaded.model_dump(mode="json")

    @tool
    def save_chat_log(question: str, answer: str) -> dict[str, object]:
        """Save a ChatOps conversation turn to S3.

        Use this to persist the current Q&A exchange for future reference.

        Args:
            question: The user question sent to the agent.
            answer: The agent response returned to the user.
        """
        uploaded = s3_service.save_chat_log(question, answer)
        return uploaded.model_dump(mode="json")

    return [list_s3_buckets, list_s3_objects, save_audit_log, save_chat_log]
