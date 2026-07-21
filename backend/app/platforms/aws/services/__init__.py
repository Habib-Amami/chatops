"""AWS service operations exposed to the application."""

from app.platforms.aws.services.ec2_service import EC2Service
from app.platforms.aws.services.s3_service import S3Service

__all__ = [
    "EC2Service",
    "S3Service",
]
