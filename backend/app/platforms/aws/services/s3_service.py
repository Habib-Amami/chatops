"""S3 bucket and object operations via LocalStack or real AWS."""

from datetime import datetime, timezone

from botocore.client import BaseClient

from app.core import Settings
from app.platforms.aws import AWSClientFactory
from app.platforms.aws.models import BucketSummary, ObjectSummary


class S3Service:
    """Provide namespace-scoped S3 bucket and object operations."""

    def __init__(
        self,
        settings: Settings,
        clients: AWSClientFactory,
    ) -> None:
        self._allowed_buckets = frozenset(settings.s3_allowed_buckets)
        self._log_bucket = settings.s3_log_bucket
        self._s3_client: BaseClient = clients.get_client("s3")

    def list_buckets(self) -> list[BucketSummary]:
        """List all accessible S3 buckets."""
        response = self._s3_client.list_buckets()
        buckets = response.get("Buckets", []) or []
        return [
            BucketSummary(
                name=bucket["Name"],
                creation_date=(
                    bucket["CreationDate"].isoformat()
                    if bucket.get("CreationDate")
                    else None
                ),
            )
            for bucket in buckets
        ]

    def list_objects(self, bucket: str, prefix: str = "") -> list[ObjectSummary]:
        """List objects in one explicitly allowed S3 bucket."""
        if bucket not in self._allowed_buckets:
            raise PermissionError(f"Bucket {bucket!r} is not allowed")

        response = self._s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        objects = response.get("Contents", []) or []
        return [
            ObjectSummary(
                key=obj["Key"],
                size=obj.get("Size", 0),
                last_modified=(
                    obj["LastModified"].isoformat() if obj.get("LastModified") else None
                ),
                bucket=bucket,
            )
            for obj in objects
        ]

    def upload_object(self, bucket: str, key: str, content: str) -> ObjectSummary:
        """Upload a text object to an allowed S3 bucket."""
        if bucket not in self._allowed_buckets:
            raise PermissionError(f"Bucket {bucket!r} is not allowed")

        self._s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
        )
        return ObjectSummary(
            key=key,
            size=len(content),
            last_modified=datetime.now(timezone.utc).isoformat(),
            bucket=bucket,
        )

    def download_object(self, bucket: str, key: str) -> str:
        """Download a text object from an allowed S3 bucket."""
        if bucket not in self._allowed_buckets:
            raise PermissionError(f"Bucket {bucket!r} is not allowed")

        response = self._s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")

    def save_audit_log(self, action: str, target: str, result: str) -> ObjectSummary:
        """Save a ChatOps audit entry to the configured log bucket."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        key = f"chatops/audit/{timestamp}_{action}_{target}.json"
        content = (
            f'{{"timestamp": "{datetime.now(timezone.utc).isoformat()}", '
            f'"action": "{action}", '
            f'"target": "{target}", '
            f'"result": "{result}"}}'
        )
        return self.upload_object(self._log_bucket, key, content)

    def save_chat_log(self, question: str, answer: str) -> ObjectSummary:
        """Save a ChatOps conversation turn to the configured log bucket."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        key = f"chatops/conversations/{timestamp}.txt"
        content = f"Q: {question}\n\nA: {answer}"
        return self.upload_object(self._log_bucket, key, content)
