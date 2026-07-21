"""Agent tools backed by the EC2 service."""

from langchain.tools import BaseTool, tool

from app.agent.tools.aws.formatters import format_ec2_instances
from app.platforms.aws.services import EC2Service


def create_ec2_tools(ec2_service: EC2Service) -> list[BaseTool]:
    """Create EC2 tools bound to an initialized service."""

    @tool
    def list_ec2_instances(state_filter: str | None = None) -> str:
        """List EC2 instances currently available in the environment.

        Use this when a user asks about EC2 instances, servers, or virtual
        machines, their status, or how many are running.
        """
        instances = ec2_service.list_instances(state_filter=state_filter)
        return format_ec2_instances(instances, state_filter)

    return [list_ec2_instances]
