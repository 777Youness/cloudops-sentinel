"""Fixtures for AWS collector tests. No test here can reach AWS:

- clients are created UNSIGNED, so they never need or look for credentials;
- the AWS config and credentials files are pointed at nothing and AWS_* variables are
  removed, so the developer's real profiles are never read;
- every client is wrapped in a botocore Stubber, which refuses any call it was not
  told to expect (an unexpected call fails the test instead of going to the network).
"""

from datetime import UTC, datetime, timedelta

import boto3
import pytest
from botocore import UNSIGNED
from botocore.config import Config
from botocore.stub import Stubber

from sentinel.collectors.aws.clients import AwsClients

REGION = "eu-west-3"
INSTANCE_ID = "i-0123456789abcdef0"


@pytest.fixture(autouse=True)
def no_real_aws(monkeypatch, tmp_path):
    for name in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))


class Stubs:
    def __init__(self) -> None:
        config = Config(
            signature_version=UNSIGNED,
            region_name=REGION,
            retries={"mode": "standard", "max_attempts": 1},
        )
        session = boto3.Session(region_name=REGION)
        self.clients = AwsClients(
            ec2=session.client("ec2", config=config),
            cloudwatch=session.client("cloudwatch", config=config),
            logs=session.client("logs", config=config),
        )
        self.ec2 = Stubber(self.clients.ec2)
        self.cloudwatch = Stubber(self.clients.cloudwatch)
        self.logs = Stubber(self.clients.logs)

    def all(self):
        return (self.ec2, self.cloudwatch, self.logs)


@pytest.fixture
def stubs():
    s = Stubs()
    for stub in s.all():
        stub.activate()
    yield s
    for stub in s.all():
        stub.assert_no_pending_responses()
        stub.deactivate()


# --- response builders ----------------------------------------------------------------------


def instance(
    instance_id=INSTANCE_ID, state="running", instance_type="t3.micro", name="cloudops-dev"
):
    return {
        "InstanceId": instance_id,
        "InstanceType": instance_type,
        "State": {"Name": state, "Code": 16},
        "Tags": [
            {"Key": "Name", "Value": name},
            {"Key": "cloudops-sentinel:monitor", "Value": "true"},
            {"Key": "Project", "Value": "cloudops-sentinel"},
        ],
    }


def describe_instances(*instances):
    return {"Reservations": [{"Instances": list(instances)}] if instances else []}


def credit_specs(mode="standard", instance_id=INSTANCE_ID):
    return {"InstanceCreditSpecifications": [{"InstanceId": instance_id, "CpuCredits": mode}]}


def five_minute_points(now: datetime, values_newest_last: list[float]):
    """Timestamps for complete 5-minute periods ending before `now`, oldest first."""
    epoch = int(now.timestamp())
    last = datetime.fromtimestamp(epoch - epoch % 300 - 300, tz=UTC)
    n = len(values_newest_last)
    stamps = [last - timedelta(minutes=5 * (n - 1 - i)) for i in range(n)]
    return stamps, values_newest_last


def metric_result(query_id, stamps, values, status="Complete"):
    return {"Id": query_id, "Timestamps": stamps, "Values": values, "StatusCode": status}


def log_row(stream, minute: datetime, **fields):
    row = [
        {"field": "@logStream", "value": stream},
        {"field": "bin(1m)", "value": minute.strftime("%Y-%m-%d %H:%M:%S.000")},
    ]
    row += [{"field": k, "value": str(v)} for k, v in fields.items()]
    return row
