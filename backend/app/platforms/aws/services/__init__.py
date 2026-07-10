"""AWS service operations exposed to the application."""

from app.platforms.aws.services.s3_service import (
    S3Service,
    BucketSummary,
    ObjectSummary,
)

__all__ = ["S3Service", "BucketSummary", "ObjectSummary"]
