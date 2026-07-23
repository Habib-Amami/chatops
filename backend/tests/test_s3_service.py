from unittest.mock import MagicMock

from app.core import Settings
from app.platforms.aws.services import S3Service


def test_audit_log_uses_configured_chatops_bucket() -> None:
    s3_client = MagicMock()
    clients = MagicMock()
    clients.get_client.return_value = s3_client
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        s3_allowed_buckets=["team-chatops-logs"],
        s3_log_bucket="team-chatops-logs",
    )
    service = S3Service(settings, clients)

    result = service.save_audit_log("scale", "deployment/api", "completed")

    assert result.bucket == "team-chatops-logs"
    put_request = s3_client.put_object.call_args.kwargs
    assert put_request["Bucket"] == "team-chatops-logs"
    assert put_request["Key"].startswith("chatops/audit/")
