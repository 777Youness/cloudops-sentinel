"""boto3 clients for the AWS collector. The only place a boto3 session is created.

Clients are created when a sync starts, not when the app starts: a missing profile or an
expired sign-in must become a failed sync with a hint, never stop the backend from
starting (principle 7: Sentinel stays usable).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config

# botocore's "standard" retry mode retries throttling and transient errors with
# exponential backoff and jitter; 3 attempts in total, then the error is reported.
RETRY_CONFIG = Config(
    retries={"mode": "standard", "max_attempts": 3},
    connect_timeout=5,
    read_timeout=20,
)


@dataclass(frozen=True)
class AwsClients:
    ec2: Any
    cloudwatch: Any
    logs: Any


ClientsFactory = Callable[[], AwsClients]


def session_clients_factory(profile: str | None, region: str) -> ClientsFactory:
    """A factory using the standard credential chain of `profile` (None: default chain)."""

    def create() -> AwsClients:
        session = boto3.Session(profile_name=profile, region_name=region)
        config = RETRY_CONFIG.merge(Config(region_name=region))
        return AwsClients(
            ec2=session.client("ec2", config=config),
            cloudwatch=session.client("cloudwatch", config=config),
            logs=session.client("logs", config=config),
        )

    return create
