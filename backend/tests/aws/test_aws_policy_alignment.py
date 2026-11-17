"""The collector code may only call what Sentinel's read-only policy allows (principle 4).

Scans collectors/aws/*.py for boto3 client calls (`ec2.describe_instances(`,
`get_paginator("describe_instances")`) and maps each to its IAM action. Every one must be
on the approved list pinned by test_readonly_policy.py, so a new AWS call is impossible
without a reviewed policy change, and no mutating call can slip in.
"""

import re
from pathlib import Path

from tests.test_readonly_policy import APPROVED_ACTIONS

AWS_PACKAGE = Path(__file__).resolve().parents[2] / "sentinel" / "collectors" / "aws"
SERVICE_PREFIX = {"ec2": "ec2", "cloudwatch": "cloudwatch", "logs": "logs"}


def _iam_action(service: str, method: str) -> str:
    return f"{SERVICE_PREFIX[service]}:" + "".join(w.capitalize() for w in method.split("_"))


def _calls() -> set[str]:
    actions = set()
    for path in AWS_PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for service, method in re.findall(r"\b(ec2|cloudwatch|logs)\.([a-z_]+)\(", text):
            if method != "get_paginator":
                actions.add(_iam_action(service, method))
        for service, method in re.findall(
            r'\b(ec2|cloudwatch|logs)\.get_paginator\("([a-z_]+)"\)', text
        ):
            actions.add(_iam_action(service, method))
    return actions


def test_the_collector_calls_the_expected_operations():
    assert _calls() == {
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceCreditSpecifications",
        "cloudwatch:GetMetricData",
        "logs:StartQuery",
        "logs:GetQueryResults",
        "logs:StopQuery",
    }


def test_every_aws_call_is_allowed_by_the_read_only_policy():
    for action in _calls():
        assert action in APPROVED_ACTIONS, f"{action} is not in sentinel-readonly.json"


def test_no_boto3_import_outside_collectors_aws_is_covered_elsewhere():
    # The import confinement itself is enforced by tests/test_architecture.py (CONFINED).
    from tests.test_architecture import CONFINED

    assert CONFINED["boto3"] == {"collectors/aws"}
    assert CONFINED["botocore"] == {"collectors/aws"}
