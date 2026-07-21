"""AWS and LocalStack integration."""

from app.platforms.aws.client import AWSClientFactory
from app.platforms.aws.services.ec2_service import EC2Service

__all__ = ["AWSClientFactory", "EC2Service"]
