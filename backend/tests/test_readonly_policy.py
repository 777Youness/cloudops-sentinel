"""Sentinel's AWS policy must stay read-only (CLAUDE.md principles 4 and 5, ADR 0016).

infra/policies/sentinel-readonly.json is the only permission Sentinel will ever have in AWS.
This test runs without AWS: it reads the JSON and fails if

  - an Allow statement grants an action that is not on the approved list below,
    or uses a wildcard, NotAction or NotResource;
  - an approved action is not a read verb, unless it is a documented exception;
  - the explicit Deny statement stops covering a representative write or remediation
    action, or contradicts an allowed action;
  - a statement on Resource "*" is not pinned to the template's region.

Adding a permission means editing APPROVED_ACTIONS here, in a reviewed change.
"""

import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[2] / "infra" / "policies" / "sentinel-readonly.json"

# Every action Sentinel's collector may perform, and why (Day 5 collectors).
APPROVED_ACTIONS = {
    "ec2:DescribeInstances": "find instances tagged cloudops-sentinel:monitor=true",
    "ec2:DescribeInstanceCreditSpecifications": "credit mode, needed by R-CPU-CREDIT",
    "cloudwatch:GetMetricData": "metric series (CPU, credits, status checks, memory)",
    "cloudwatch:DescribeAlarms": "alarm states of the workload's own alarms",
    "logs:StartQuery": "Logs Insights query over the workload access log (exception below)",
    "logs:GetQueryResults": "read the result of that query",
    "logs:StopQuery": "cancel Sentinel's own query on timeout (exception below)",
    "logs:FilterLogEvents": "bounded log samples as evidence",
    "ssm:ListCommands": "deployment events: history of the operator's deploy commands",
}

READ_VERBS = ("Describe", "Get", "List", "Filter")

# Allowed although their verb is not a read verb. Both are Logs Insights query control:
# they do not change any AWS resource or data.
QUERY_CONTROL_EXCEPTIONS = {
    "logs:StartQuery": "Starts a read-only Logs Insights query and returns a query id. It "
    "changes no resource or log data. It is billed per GB scanned, so Sentinel calls it "
    "only during sync, over a bounded time window.",
    "logs:StopQuery": "Cancels a query Sentinel itself started (e.g. on timeout). It "
    "changes no resource or log data and stops further scanning cost.",
}

# Representative write and remediation actions (CLAUDE.md principle 4 verbs) that the
# explicit Deny must cover even if someone later attaches a broader policy to the role.
MUST_BE_DENIED = [
    "ec2:StartInstances",
    "ec2:StopInstances",
    "ec2:RebootInstances",
    "ec2:TerminateInstances",
    "ec2:RunInstances",
    "ec2:ModifyInstanceAttribute",
    "ec2:CreateSnapshot",
    "ec2:DeleteVolume",
    "ec2:AuthorizeSecurityGroupIngress",
    "ec2:RevokeSecurityGroupEgress",
    "ec2:AssociateIamInstanceProfile",
    "ssm:SendCommand",
    "ssm:StartSession",
    "ssm:StartAutomationExecution",
    "ssm:PutParameter",
    "ssm:UpdateInstanceInformation",
    "cloudwatch:PutMetricData",
    "cloudwatch:PutMetricAlarm",
    "cloudwatch:SetAlarmState",
    "cloudwatch:DeleteAlarms",
    "cloudwatch:DisableAlarmActions",
    "logs:PutLogEvents",
    "logs:CreateLogStream",
    "logs:DeleteLogGroup",
    "logs:PutRetentionPolicy",
    "iam:CreateUser",
    "iam:AttachRolePolicy",
    "iam:PassRole",
    "sts:AssumeRole",
]

TEMPLATE_VARIABLES = {"region", "account_id", "log_group_name"}

# Resource scope per action, from the Service Authorization Reference (checked 2026-10-12):
#   list_ec2.html   DescribeInstances, DescribeInstanceCreditSpecifications: no resource
#                   type (so "*"), access level List, condition key ec2:Region
#   list_cloudwatch GetMetricData: optional "dataset" only (so "*"), Read
#                   DescribeAlarms: alarm* required, Read,
#                   arn:${Partition}:cloudwatch:${Region}:${Account}:alarm:${AlarmName}
#   list_logs.html  StartQuery, GetQueryResults, FilterLogEvents: log-group* required, Read,
#                   arn:${Partition}:logs:${Region}:${Account}:log-group:${LogGroupName}
#                   StopQuery: no resource type (so "*"), Read
#   list_ssm.html   ListCommands: no resource type (so "*"), List
LOG_GROUP = "arn:aws:logs:${region}:${account_id}:log-group:${log_group_name}"
ALARMS = "arn:aws:cloudwatch:${region}:${account_id}:alarm:cloudops-sentinel-*"
EXPECTED_SCOPE = {
    "ec2:DescribeInstances": "*",
    "ec2:DescribeInstanceCreditSpecifications": "*",
    "cloudwatch:GetMetricData": "*",
    "cloudwatch:DescribeAlarms": ALARMS,
    "logs:StartQuery": LOG_GROUP,
    "logs:GetQueryResults": LOG_GROUP,
    "logs:FilterLogEvents": LOG_GROUP,
    "logs:StopQuery": "*",
    "ssm:ListCommands": "*",
}

# Read-level actions Sentinel must never perform: logs:Unmask would reveal data that a
# CloudWatch Logs data protection policy masks as sensitive.
SENSITIVE_READS_DENIED = ["logs:Unmask"]


def _policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _as_list(value):
    return value if isinstance(value, list) else [value]


def _statements(effect):
    return [s for s in _policy()["Statement"] if s["Effect"] == effect]


def _allowed():
    return [a for s in _statements("Allow") for a in _as_list(s["Action"])]


def _deny_patterns():
    return [a for s in _statements("Deny") for a in _as_list(s["Action"])]


def test_policy_is_valid_json_with_known_effects():
    policy = _policy()
    assert policy["Version"] == "2012-10-17"
    assert {s["Effect"] for s in policy["Statement"]} == {"Allow", "Deny"}
    sids = [s["Sid"] for s in policy["Statement"]]
    assert len(sids) == len(set(sids))


def test_allowed_actions_are_exactly_the_approved_list():
    allowed = _allowed()
    assert len(allowed) == len(set(allowed)), "an action is granted twice"
    assert set(allowed) == set(APPROVED_ACTIONS)


def test_allow_statements_use_no_wildcards_or_negations():
    for statement in _statements("Allow"):
        assert "NotAction" not in statement and "NotResource" not in statement
        for action in _as_list(statement["Action"]):
            assert "*" not in action and "?" not in action, action


def test_every_allowed_action_is_a_read_or_a_documented_exception():
    for action in _allowed():
        verb = action.split(":", 1)[1]
        if verb.startswith(READ_VERBS):
            continue
        assert action in QUERY_CONTROL_EXCEPTIONS, f"{action} is not a read action"


def test_exceptions_are_only_logs_insights_query_control():
    assert set(QUERY_CONTROL_EXCEPTIONS) == {"logs:StartQuery", "logs:StopQuery"}
    assert set(QUERY_CONTROL_EXCEPTIONS) <= set(_allowed())


def test_write_and_remediation_actions_are_explicitly_denied():
    patterns = _deny_patterns()
    for action in MUST_BE_DENIED:
        assert any(fnmatchcase(action, p) for p in patterns), f"{action} is not denied"


def test_the_deny_does_not_contradict_an_allowed_action():
    patterns = _deny_patterns()
    for action in _allowed():
        matching = [p for p in patterns if fnmatchcase(action, p)]
        assert not matching, f"{action} is allowed but denied by {matching}"


def test_statements_on_all_resources_are_pinned_to_the_region():
    for statement in _statements("Allow"):
        if "*" in _as_list(statement["Resource"]):
            condition = statement.get("Condition", {}).get("StringEquals", {})
            assert condition.get("aws:RequestedRegion") == "${region}", statement["Sid"]


def test_scoped_resources_stay_inside_the_project():
    for statement in _statements("Allow"):
        for resource in _as_list(statement["Resource"]):
            if resource == "*":
                continue
            assert "${account_id}" in resource and "${region}" in resource, resource
            assert "cloudops-sentinel" in resource or "${log_group_name}" in resource, resource


def test_each_action_has_exactly_the_documented_scope():
    assert set(EXPECTED_SCOPE) == set(APPROVED_ACTIONS)
    for statement in _statements("Allow"):
        resources = _as_list(statement["Resource"])
        for action in _as_list(statement["Action"]):
            assert resources == [EXPECTED_SCOPE[action]], f"{action}: {resources}"


def test_sensitive_reads_are_explicitly_denied():
    patterns = _deny_patterns()
    for action in SENSITIVE_READS_DENIED:
        assert any(fnmatchcase(action, p) for p in patterns), f"{action} is not denied"
        assert action not in _allowed()


def test_only_known_template_variables_are_used():
    used = set(re.findall(r"\$\{([a-z_]+)\}", POLICY_PATH.read_text(encoding="utf-8")))
    assert used == TEMPLATE_VARIABLES
