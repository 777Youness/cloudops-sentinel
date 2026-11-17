"""Discover the monitored EC2 instances (tag cloudops-sentinel:monitor=true).

Calls: ec2:DescribeInstances, ec2:DescribeInstanceCreditSpecifications (both allowed by
infra/policies/sentinel-readonly.json, region-pinned).
"""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from sentinel.collectors.aws.errors import translate
from sentinel.domain.observations import InstanceState, Resource
from sentinel.domain.system import CollectorError

MONITOR_TAG = "cloudops-sentinel:monitor"
# Terminated instances are gone; everything else is reported, including stopped ones.
LISTED_STATES = ["pending", "running", "stopping", "stopped"]
KNOWN_STATES = {"pending", "running", "stopping", "stopped", "terminated"}


def is_burstable(instance_type: str) -> bool:
    """T-family instances (t2, t3, t3a, t4g) earn and spend CPU credits."""
    return instance_type.split(".")[0].startswith("t")


def _resource(instance: dict[str, Any], region: str) -> Resource:
    tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
    state = instance.get("State", {}).get("Name", "unknown")
    resolved: InstanceState = state if state in KNOWN_STATES else "unknown"  # type: ignore[assignment]
    return Resource(
        id=instance["InstanceId"],
        name=tags.get("Name", instance["InstanceId"]),
        region=region,
        state=resolved,
        instance_type=instance["InstanceType"],
        credit_mode=None,  # filled from DescribeInstanceCreditSpecifications
        tags=tags,
        data_origin="aws",
    )


def discover_instances(ec2: Any, region: str) -> list[Resource]:
    """Every monitored instance that is not terminated. Raises on any AWS error: without
    discovery there is nothing to collect."""
    resources = []
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[
            {"Name": f"tag:{MONITOR_TAG}", "Values": ["true"]},
            {"Name": "instance-state-name", "Values": LISTED_STATES},
        ]
    )
    for page in pages:
        for reservation in page.get("Reservations", []):
            resources += [_resource(i, region) for i in reservation.get("Instances", [])]
    return sorted(resources, key=lambda r: r.id)


def add_credit_modes(ec2: Any, resources: list[Resource]) -> CollectorError | None:
    """Set credit_mode on burstable instances. Returns the error if the call failed.

    On failure credit_mode stays None, R-CPU-CREDIT then reports not_applicable, so the
    caller must mark discovery as DEGRADED: the check was not done, it did not pass.
    """
    burstable = [r for r in resources if is_burstable(r.instance_type)]
    if not burstable:
        return None
    try:
        response = ec2.describe_instance_credit_specifications(
            InstanceIds=[r.id for r in burstable]
        )
    except (ClientError, BotoCoreError) as exc:
        return translate(exc, what="ec2:DescribeInstanceCreditSpecifications")
    modes = {
        spec["InstanceId"]: spec.get("CpuCredits")
        for spec in response.get("InstanceCreditSpecifications", [])
    }
    for resource in burstable:
        mode = modes.get(resource.id)
        if mode in ("standard", "unlimited"):
            resource.credit_mode = mode
    return None
