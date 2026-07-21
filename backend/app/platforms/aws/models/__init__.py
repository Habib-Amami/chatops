"""Normalized AWS result models."""

from app.platforms.aws.models.ec2_models import EC2InstanceSummary
from app.platforms.aws.models.s3_models import BucketSummary, ObjectSummary

__all__ = [
    "BucketSummary",
    "EC2InstanceSummary",
    "ObjectSummary",
]
