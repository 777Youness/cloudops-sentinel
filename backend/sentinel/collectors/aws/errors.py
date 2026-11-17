"""AWS errors -> CollectorError with a stable code and a human hint (CLAUDE.md section 8).

The one place where boto3/botocore failures are interpreted. Every message is passed
through mask_account_ids: AWS error messages often quote ARNs, and the account id is shown
with its last 4 digits only (CLAUDE.md section 7). Credentials never appear in botocore
error messages; nothing here reads or prints them.
"""

import re

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionError,
    CredentialRetrievalError,
    HTTPClientError,
    InvalidConfigError,
    LoginError,
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
    TokenRetrievalError,
)

from sentinel.domain.system import CollectorError

LOGIN_HINT = (
    "Sign in again: aws login --profile sentinel-login (the sentinel profile assumes the "
    "read-only role through it; see infra/README.md)."
)

ACCESS_DENIED = {
    "AccessDenied",
    "AccessDeniedException",
    "UnauthorizedOperation",
    "UnauthorizedException",
}
EXPIRED = {
    "ExpiredToken",
    "ExpiredTokenException",
    "RequestExpired",
    "InvalidClientTokenId",
    "UnrecognizedClientException",
}
THROTTLED = {
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
    "TooManyRequestsException",
    "LimitExceededException",
}
NOT_FOUND = {"ResourceNotFoundException"}

_ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")
MAX_MESSAGE = 300


def mask_account_ids(text: str) -> str:
    """123456789012 -> ********9012."""
    return _ACCOUNT_ID.sub(lambda m: "********" + m.group(0)[-4:], text)


def _clip(text: str) -> str:
    text = mask_account_ids(text)
    return text if len(text) <= MAX_MESSAGE else text[: MAX_MESSAGE - 1] + "…"


def translate(exc: Exception, *, what: str) -> CollectorError:
    """`what` says which call failed, e.g. "ec2:DescribeInstances"."""
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        message = _clip(f"{what}: {code}: {error.get('Message', '')}".rstrip(": "))
        if code in ACCESS_DENIED:
            return CollectorError(
                code="access_denied",
                message=message,
                hint="The read-only role does not allow this call. Compare "
                "infra/policies/sentinel-readonly.json with the role in IAM; never widen "
                "it to a wildcard.",
            )
        if code in EXPIRED:
            return CollectorError(code="credentials_expired", message=message, hint=LOGIN_HINT)
        if code in THROTTLED:
            return CollectorError(
                code="throttled",
                message=message,
                hint="AWS is rate-limiting requests (already retried). Wait a minute, then "
                "sync again.",
            )
        if code in NOT_FOUND:
            return CollectorError(
                code="not_found",
                message=message,
                hint="The workload's log group does not exist: is the workload deployed "
                "(terraform apply), and does SENTINEL_AWS_LOG_GROUP match it?",
            )
        return CollectorError(code="aws_error", message=message)

    message = _clip(f"{what}: {type(exc).__name__}: {exc}")
    if isinstance(exc, ProfileNotFound | InvalidConfigError):
        return CollectorError(
            code="profile_not_configured",
            message=message,
            hint="Create the sentinel profile in ~/.aws/config (infra/README.md, Profiles) "
            "or set SENTINEL_AWS_PROFILE.",
        )
    credential_errors = (
        NoCredentialsError,
        PartialCredentialsError,
        CredentialRetrievalError,  # e.g. credential_process failed: aws login expired
        TokenRetrievalError,
        LoginError,
    )
    if isinstance(exc, credential_errors):
        return CollectorError(code="credentials_unavailable", message=message, hint=LOGIN_HINT)
    if isinstance(exc, ConnectionError | HTTPClientError):
        return CollectorError(
            code="unreachable",
            message=message,
            hint="Check the network connection and the region (eu-west-3).",
        )
    if isinstance(exc, BotoCoreError):
        return CollectorError(code="aws_error", message=message)
    return CollectorError(code=type(exc).__name__, message=message)
