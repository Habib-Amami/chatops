from typing import Any
from unittest.mock import MagicMock

from langchain_core.messages import ToolMessage

from app.agent.tools.aws import create_ec2_tools, create_s3_tools
from app.platforms.aws.models import (
    BucketSummary,
    EC2InstanceSummary,
    ObjectSummary,
)


def _tools_by_name(tools: list[Any]) -> dict[str, Any]:
    return {tool.name: tool for tool in tools}


def test_empty_s3_bucket_result_produces_string_tool_message() -> None:
    s3_service = MagicMock()
    s3_service.list_buckets.return_value = []
    tool = _tools_by_name(create_s3_tools(s3_service))["list_s3_buckets"]

    result = tool.invoke(
        {
            "name": "list_s3_buckets",
            "args": {},
            "id": "s3-buckets-1",
            "type": "tool_call",
        }
    )

    assert isinstance(result, ToolMessage)
    assert result.content == "No S3 buckets were found."
    assert isinstance(result.content, str)


def test_s3_bucket_tool_formats_structured_service_results() -> None:
    s3_service = MagicMock()
    s3_service.list_buckets.return_value = [
        BucketSummary(
            name="opstasks-logs",
            creation_date="2026-07-21T10:00:00+00:00",
        )
    ]
    tool = _tools_by_name(create_s3_tools(s3_service))["list_s3_buckets"]

    result = tool.invoke({})

    assert result == (
        "S3 buckets:\n- opstasks-logs: created_at=2026-07-21T10:00:00+00:00"
    )


def test_s3_object_tool_formats_empty_and_non_empty_results() -> None:
    s3_service = MagicMock()
    tool = _tools_by_name(create_s3_tools(s3_service))["list_s3_objects"]
    s3_service.list_objects.return_value = []

    empty_result = tool.invoke({"bucket": "opstasks-logs", "prefix": "audit/"})

    assert empty_result == (
        "No S3 objects were found in bucket 'opstasks-logs' with prefix 'audit/'."
    )

    s3_service.list_objects.return_value = [
        ObjectSummary(
            key="audit/event.json",
            size=128,
            last_modified="2026-07-21T10:05:00+00:00",
            bucket="opstasks-logs",
        )
    ]

    result = tool.invoke({"bucket": "opstasks-logs", "prefix": "audit/"})

    assert result == (
        "S3 objects in bucket 'opstasks-logs' with prefix 'audit/':\n"
        "- audit/event.json: size_bytes=128, "
        "last_modified=2026-07-21T10:05:00+00:00"
    )


def test_empty_ec2_result_produces_string_tool_message() -> None:
    ec2_service = MagicMock()
    ec2_service.list_instances.return_value = []
    tool = _tools_by_name(create_ec2_tools(ec2_service))["list_ec2_instances"]

    result = tool.invoke(
        {
            "name": "list_ec2_instances",
            "args": {"state_filter": "running"},
            "id": "ec2-list-1",
            "type": "tool_call",
        }
    )

    assert isinstance(result, ToolMessage)
    assert result.content == "No EC2 instances were found with state 'running'."
    assert isinstance(result.content, str)


def test_ec2_tool_formats_structured_service_results() -> None:
    ec2_service = MagicMock()
    ec2_service.list_instances.return_value = [
        EC2InstanceSummary(
            instance_id="i-1234567890",
            instance_type="t3.micro",
            state="running",
            private_ip="10.0.0.5",
            public_ip=None,
            launch_time="2026-07-21T10:00:00+00:00",
        )
    ]
    tool = _tools_by_name(create_ec2_tools(ec2_service))["list_ec2_instances"]

    result = tool.invoke({})

    assert result == (
        "EC2 instances:\n"
        "- i-1234567890: state=running, type=t3.micro, "
        "private_ip=10.0.0.5, public_ip=none, "
        "launched_at=2026-07-21T10:00:00+00:00"
    )
