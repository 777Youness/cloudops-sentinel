"""AWS errors become stable codes with a hint; account ids are always masked."""

import pytest
from botocore.exceptions import (
    ClientError,
    CredentialRetrievalError,
    EndpointConnectionError,
    NoCredentialsError,
    ProfileNotFound,
)

from sentinel.collectors.aws.errors import mask_account_ids, translate


def client_error(code, message="details"):
    return ClientError({"Error": {"Code": code, "Message": message}}, "AnyOperation")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AccessDenied", "access_denied"),
        ("AccessDeniedException", "access_denied"),
        ("UnauthorizedOperation", "access_denied"),
        ("ExpiredToken", "credentials_expired"),
        ("ExpiredTokenException", "credentials_expired"),
        ("RequestExpired", "credentials_expired"),
        ("Throttling", "throttled"),
        ("ThrottlingException", "throttled"),
        ("RequestLimitExceeded", "throttled"),
        ("ResourceNotFoundException", "not_found"),
        ("SomethingNew", "aws_error"),
    ],
)
def test_client_errors_map_to_stable_codes(code, expected):
    error = translate(client_error(code), what="ec2:DescribeInstances")
    assert error.code == expected
    assert error.message.startswith(f"ec2:DescribeInstances: {code}")


def test_access_denied_and_expired_errors_explain_what_to_do():
    assert "sentinel-readonly.json" in translate(client_error("AccessDenied"), what="x").hint
    assert (
        "aws login --profile sentinel-login"
        in translate(client_error("ExpiredToken"), what="x").hint
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ProfileNotFound(profile="sentinel"), "profile_not_configured"),
        (NoCredentialsError(), "credentials_unavailable"),
        (
            CredentialRetrievalError(provider="process", error_msg="expired"),
            "credentials_unavailable",
        ),
        (
            EndpointConnectionError(endpoint_url="https://ec2.eu-west-3.amazonaws.com"),
            "unreachable",
        ),
    ],
)
def test_local_credential_and_network_errors(exc, expected):
    error = translate(exc, what="ec2:DescribeInstances")
    assert error.code == expected
    assert error.hint


def test_account_ids_are_masked_in_every_message():
    message = "User: arn:aws:sts::123456789012:assumed-role/x is not authorized"
    error = translate(client_error("AccessDenied", message), what="cloudwatch:GetMetricData")
    assert "123456789012" not in error.message
    assert "********9012" in error.message
    assert mask_account_ids("id 123456789012, port 8080") == "id ********9012, port 8080"


def test_messages_are_bounded():
    error = translate(client_error("AccessDenied", "x" * 5000), what="ec2:DescribeInstances")
    assert len(error.message) <= 300
