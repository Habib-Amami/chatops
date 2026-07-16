"""Agent tools backed by the EC2 service."""

from langchain.tools import BaseTool, tool

from app.platforms.aws.services import EC2Service


def create_ec2_tools(ec2_service: EC2Service) -> list[BaseTool]:
    """Create EC2 tools bound to an initialized service."""

    @tool
    def list_ec2_instances(state_filter: str | None = None) -> list[dict[str, object]]:
        """List EC2 instances currently available in the environment.

        Use this when a user asks about EC2 instances, servers, or virtual
        machines, their status, or how many are running.
        """
        instances = ec2_service.list_instances(state_filter=state_filter)
        return [instance.model_dump(mode="json") for instance in instances]

    return [list_ec2_instances]