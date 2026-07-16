"""Read-only EC2 operations."""

from pydantic import BaseModel

from app.platforms.aws import AWSClientFactory


class EC2InstanceSummary(BaseModel):
    """Small, agent-safe representation of an EC2 instance."""

    instance_id: str
    instance_type: str
    state: str
    private_ip: str | None
    public_ip: str | None
    launch_time: str | None


class EC2Service:
    """Provide read-only EC2 instance operations."""

    def __init__(self, clients: AWSClientFactory) -> None:
        self._ec2_client = clients.get_client("ec2")

    def list_instances(
        self, state_filter: str | None = None
    ) -> list[EC2InstanceSummary]:
        """List EC2 instances, optionally filtered by state
        (e.g. 'running', 'stopped', 'terminated')."""
        filters = (
            [{"Name": "instance-state-name", "Values": [state_filter]}]
            if state_filter
            else []
        )

        response = self._ec2_client.describe_instances(Filters=filters)

        instances: list[EC2InstanceSummary] = []
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instances.append(
                    EC2InstanceSummary(
                        instance_id=instance["InstanceId"],
                        instance_type=instance["InstanceType"],
                        state=instance["State"]["Name"],
                        private_ip=instance.get("PrivateIpAddress"),
                        public_ip=instance.get("PublicIpAddress"),
                        launch_time=(
                            str(instance["LaunchTime"])
                            if instance.get("LaunchTime")
                            else None
                        ),
                    )
                )
        return instances