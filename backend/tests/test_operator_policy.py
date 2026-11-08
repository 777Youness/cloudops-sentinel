"""The operator's Terraform policy must stay scoped (ADR 0017, decision D2).

infra/policies/operator-terraform.json is attached BY HAND to the operator's IAM user; it
is never created by Terraform. It must let Terraform build the dev workload and nothing
more: no long-lived credentials, no Organizations or IAM Identity Center (they would expire
the account's credits), no forbidden resources, and no wildcard services.

Like test_readonly_policy.py this reads the JSON, with no AWS access. It cannot prove the
policy is SUFFICIENT for Terraform; only a real `terraform plan` / `apply` shows that
(infra/README.md, AccessDenied loop). It proves the policy is not too broad.
"""

import importlib.util
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "infra" / "policies" / "operator-terraform.json"
READONLY_PATH = ROOT / "infra" / "policies" / "sentinel-readonly.json"

_spec = importlib.util.spec_from_file_location(
    "render_policy", ROOT / "scripts" / "render_policy.py"
)
render_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_policy)

VARIABLES = {"region": "eu-west-3", "account_id": "111122223333", "log_group_name": "/x"}

# AWS quota: a customer managed policy may hold at most 6,144 characters, whitespace not
# counted (IAM and STS quotas). The example account id has 12 digits like every real one,
# so the rendered size here is the size you will paste. Margin kept below the hard limit.
IAM_MANAGED_POLICY_MAX_CHARS = 6144
SIZE_TARGET_CHARS = 6000

# Sids are short because they count toward the size limit. Their meaning lives here, and
# the test below fails if a statement is added, removed or renamed without updating it.
SID_PURPOSES = {
    "Ec2Read": "ec2:Describe* in the region (Terraform reads)",
    "Network": "create/delete the VPC, subnet, IGW, routes, security groups, tags",
    "RunT3Micro": "RunInstances: instance must be t3.micro with IMDSv2",
    "RunGp3Enc": "RunInstances: volumes must be encrypted gp3",
    "RunAmazonAmi": "RunInstances: image and snapshot owned by Amazon",
    "RunInVpc": "RunInstances: network interface, security group, subnet",
    "TaggedInst": "terminate/modify only instances tagged Project=cloudops-sentinel",
    "EbsKms": "use the EBS KMS key only through EC2",
    "EbsGrant": "KMS grants only for AWS resources, through EC2",
    "RoleProfile": "manage roles and instance profiles named cloudops-sentinel-*",
    "AttachSsm": "attach only AmazonSSMManagedInstanceCore",
    "PassToEc2": "pass cloudops-sentinel-* roles to EC2 only",
    "LogGroup": "manage log groups /cloudops-sentinel/*",
    "ListLogs": "list log groups in the region",
    "Alarms": "manage alarms cloudops-sentinel-*",
    "AmiParam": "read the public AL2023 AMI parameter",
    "ShellInst": "Session Manager on project-tagged instances",
    "ShellDoc": "the Session Manager shell document",
    "OwnSessions": "terminate/resume only your own sessions",
    "CheckReads": "reads for scripts/cost-check.sh",
    "CheckIam": "IAM listing for scripts/cost-check.sh",
    "DenyRisky": "explicit Deny: long-lived credentials, Organizations, Identity Center, "
    "forbidden resources",
}

# Allowed wildcard actions, each with a reason. Everything else is an exact action name.
ALLOWED_WILDCARD_ACTIONS = {
    "ec2:Describe*": "Terraform reads many EC2 attributes; Describe calls change nothing "
    "and have no resource-level permissions. Pinned to the region.",
}

# Must never be allowed (CLAUDE.md sections 6 and 7, ADR 0017).
NEVER_ALLOWED = [
    "iam:CreateUser",
    "iam:CreateAccessKey",
    "iam:UpdateAccessKey",
    "iam:CreateLoginProfile",
    "iam:UpdateLoginProfile",
    "iam:CreatePolicy",
    "iam:CreatePolicyVersion",
    "iam:PutUserPolicy",
    "iam:AttachUserPolicy",
    "organizations:CreateOrganization",
    "sso:CreateInstance",
    "ec2:AllocateAddress",
    "ec2:CreateNatGateway",
    "ec2:CreateVpcEndpoint",
    "ec2:CreateKeyPair",
    "ec2:ImportKeyPair",
    "ec2:MonitorInstances",
    "elasticloadbalancing:CreateLoadBalancer",
    "rds:CreateDBInstance",
    "ecs:CreateCluster",
    "eks:CreateCluster",
    "kms:CreateKey",
    "secretsmanager:CreateSecret",
    "cloudtrail:CreateTrail",
    "cloudwatch:PutDashboard",
    "lambda:CreateFunction",
    "events:PutRule",
    "sns:CreateTopic",
]

# Explicitly denied, so a broader policy attached later cannot grant them either.
MUST_BE_DENIED = [
    "iam:CreateUser",
    "iam:CreateAccessKey",
    "iam:CreateLoginProfile",
    "organizations:CreateOrganization",
    "organizations:InviteAccountToOrganization",
    "sso:CreateInstance",
    "identitystore:CreateUser",
    "ec2:AllocateAddress",
    "ec2:CreateNatGateway",
    "ec2:CreateVpcEndpoint",
    "ec2:CreateKeyPair",
    "ec2:MonitorInstances",
    "kms:CreateKey",
]


def _policy() -> dict:
    return json.loads(render_policy.render(POLICY_PATH.read_text(encoding="utf-8"), VARIABLES))


def _as_list(value):
    return value if isinstance(value, list) else [value]


def _statements(effect):
    return [s for s in _policy()["Statement"] if s["Effect"] == effect]


def _allowed_actions():
    return [a for s in _statements("Allow") for a in _as_list(s["Action"])]


def _allows(action: str) -> bool:
    return any(fnmatchcase(action, a) for a in _allowed_actions())


def _denies(action: str) -> bool:
    return any(fnmatchcase(action, a) for s in _statements("Deny") for a in _as_list(s["Action"]))


def test_policy_renders_to_valid_json_with_unique_sids():
    policy = _policy()
    assert policy["Version"] == "2012-10-17"
    sids = [s["Sid"] for s in policy["Statement"]]
    assert len(sids) == len(set(sids))


def test_rendered_policy_fits_the_iam_managed_policy_size_limit():
    rendered = render_policy.render(POLICY_PATH.read_text(encoding="utf-8"), VARIABLES)
    size = len(re.sub(r"\s", "", rendered))
    assert size <= IAM_MANAGED_POLICY_MAX_CHARS, f"{size} > {IAM_MANAGED_POLICY_MAX_CHARS}"
    assert size < SIZE_TARGET_CHARS, f"{size} chars: margin below the AWS limit is too thin"


def test_every_sid_is_short_alphanumeric_and_documented():
    sids = [s["Sid"] for s in _policy()["Statement"]]
    assert sids == list(SID_PURPOSES), "update SID_PURPOSES with the policy"
    for sid in sids:
        assert re.fullmatch(r"[A-Za-z0-9]{1,16}", sid), sid  # IAM allows only A-Z, a-z, 0-9


def test_rendering_rejects_unknown_variables_and_keeps_iam_policy_variables():
    with pytest.raises(KeyError):
        render_policy.render("${region} ${unknown}", {"region": "eu-west-3"})
    assert render_policy.render("$${aws:username}", {}) == "${aws:username}"
    rendered = json.dumps(_policy())
    assert "${aws:username}" in rendered
    assert "${region}" not in rendered and "${account_id}" not in rendered


def test_no_allow_statement_uses_not_action_or_not_resource():
    for statement in _statements("Allow"):
        assert "NotAction" not in statement and "NotResource" not in statement


def test_wildcard_actions_are_only_the_documented_ones():
    for action in _allowed_actions():
        if "*" in action or "?" in action:
            assert action in ALLOWED_WILDCARD_ACTIONS, action
    assert "*" not in _allowed_actions()


@pytest.mark.parametrize("action", NEVER_ALLOWED)
def test_never_allows(action):
    assert not _allows(action), f"{action} must never be allowed"


@pytest.mark.parametrize("action", MUST_BE_DENIED)
def test_explicitly_denies(action):
    assert _denies(action), f"{action} must be explicitly denied"


def test_the_deny_does_not_block_what_terraform_needs():
    for action in ("ec2:RunInstances", "ec2:CreateVpc", "iam:CreateRole", "iam:PassRole"):
        assert _allows(action) and not _denies(action), action


def test_statements_on_all_resources_are_region_pinned_except_iam_listing():
    for statement in _statements("Allow"):
        if "*" in _as_list(statement["Resource"]):
            actions = _as_list(statement["Action"])
            if all(a.startswith("iam:List") for a in actions):
                continue  # IAM is global; listing names changes nothing
            region = statement.get("Condition", {}).get("StringEquals", {})
            assert region.get("aws:RequestedRegion") == "eu-west-3", statement["Sid"]


def test_scoped_resources_stay_in_the_account_and_region():
    for statement in _statements("Allow"):
        for resource in _as_list(statement["Resource"]):
            if resource == "*":
                continue
            assert resource.startswith("arn:aws:"), resource
            service = resource.split(":")[2]
            if service == "iam":
                assert ":111122223333:" in resource
            elif resource.startswith(("arn:aws:ec2:eu-west-3::", "arn:aws:ssm:eu-west-3::")):
                pass  # AWS-owned: AMIs, their snapshots, public SSM parameters
            else:
                assert ":eu-west-3:111122223333:" in resource, resource


def test_run_instances_is_limited_to_the_workload_shape():
    by_resource = {}
    for statement in _statements("Allow"):
        if "ec2:RunInstances" in _as_list(statement["Action"]):
            for resource in _as_list(statement["Resource"]):
                by_resource[resource.split(":")[-1].split("/")[0]] = statement.get("Condition", {})
    assert set(by_resource) == {
        "instance",
        "volume",
        "image",
        "snapshot",
        "network-interface",
        "security-group",
        "subnet",
    }
    assert by_resource["instance"]["StringEquals"] == {
        "ec2:InstanceType": "t3.micro",
        "ec2:MetadataHttpTokens": "required",
    }
    assert by_resource["volume"]["Bool"] == {"ec2:Encrypted": "true"}
    assert by_resource["volume"]["StringEquals"] == {"ec2:VolumeType": "gp3"}
    assert by_resource["image"]["StringEquals"] == {"ec2:Owner": "amazon"}


def test_pass_role_only_to_ec2_and_only_project_roles():
    statements = [s for s in _statements("Allow") if "iam:PassRole" in _as_list(s["Action"])]
    assert len(statements) == 1
    statement = statements[0]
    assert _as_list(statement["Resource"]) == ["arn:aws:iam::111122223333:role/cloudops-sentinel-*"]
    assert statement["Condition"]["StringEquals"] == {"iam:PassedToService": "ec2.amazonaws.com"}


def test_attach_role_policy_only_for_the_ssm_core_policy():
    statements = [
        s for s in _statements("Allow") if "iam:AttachRolePolicy" in _as_list(s["Action"])
    ]
    assert len(statements) == 1
    condition = statements[0]["Condition"]["ArnEquals"]["iam:PolicyARN"]
    assert condition == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"


def test_iam_writes_are_limited_to_project_roles_and_profiles():
    for statement in _statements("Allow"):
        writes = [
            a
            for a in _as_list(statement["Action"])
            if a.startswith("iam:") and not a.startswith("iam:List")
        ]
        if not writes:
            continue
        for resource in _as_list(statement["Resource"]):
            assert re.match(
                r"^arn:aws:iam::111122223333:(role|instance-profile)/cloudops-sentinel-\*$",
                resource,
            ), resource


def test_kms_use_is_only_through_ec2():
    for statement in _statements("Allow"):
        if any(a.startswith("kms:") for a in _as_list(statement["Action"])):
            assert (
                statement["Condition"]["StringEquals"]["kms:ViaService"]
                == "ec2.eu-west-3.amazonaws.com"
            )
            if "kms:CreateGrant" in _as_list(statement["Action"]):
                assert statement["Condition"]["Bool"]["kms:GrantIsForAWSResource"] == "true"


def test_instance_changes_require_the_project_tag():
    for statement in _statements("Allow"):
        actions = _as_list(statement["Action"])
        if any(a in actions for a in ("ec2:TerminateInstances", "ssm:StartSession")) and any(
            ":instance/" in r for r in _as_list(statement["Resource"])
        ):
            tag = statement["Condition"]["StringEquals"]["aws:ResourceTag/Project"]
            assert tag == "cloudops-sentinel"


def test_operator_policy_and_sentinel_readonly_policy_stay_separate():
    readonly = json.loads(
        render_policy.render(READONLY_PATH.read_text(encoding="utf-8"), VARIABLES)
    )
    readonly_sids = {s["Sid"] for s in readonly["Statement"]}
    assert not readonly_sids & {s["Sid"] for s in _policy()["Statement"]}
    # Sentinel's role must never be able to do what the operator does.
    readonly_allowed = {
        a for s in readonly["Statement"] if s["Effect"] == "Allow" for a in _as_list(s["Action"])
    }
    for action in ("ec2:RunInstances", "iam:PassRole", "iam:CreateRole", "ssm:StartSession"):
        assert action not in readonly_allowed
