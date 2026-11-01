"""Guardrails for the Terraform workload (CLAUDE.md section 6, ADR 0016, ADR 0017).

These tests read the files in infra/ and scripts/ as text. They need no AWS access, no
credentials and no Terraform binary, so they run in CI with the backend suite.

Limitation, on purpose: they are text checks, not a Terraform evaluation (`terraform test`
is "Later" in CLAUDE.md and no HCL parser is an approved dependency). They catch the
mistakes that matter here (a forbidden resource, port 22, a missing safety setting, a
mutating call in the leftover check), not every possible misconfiguration. Real behaviour
still has to be verified on AWS (infra/README.md, "Verification on AWS").
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "infra" / "envs" / "dev"
TEMPLATES = DEV / "templates"
COST_CHECK = ROOT / "scripts" / "cost-check.sh"
APP = ROOT / "workload" / "app.py"

# CLAUDE.md section 6 forbidden resources, plus things this project never creates.
FORBIDDEN_RESOURCE_TYPES = [
    "aws_nat_gateway",
    "aws_eip",
    "aws_eip_association",
    "aws_lb",
    "aws_alb",
    "aws_elb",
    "aws_db_instance",
    "aws_rds_cluster",
    "aws_ecs_",
    "aws_eks_",
    "aws_vpc_endpoint",
    "aws_kms_key",
    "aws_secretsmanager_",
    "aws_cloudtrail",
    "aws_cloudwatch_dashboard",
    "aws_key_pair",
    "aws_launch_template",
    "aws_autoscaling_group",
    "aws_iam_user",
    "aws_iam_access_key",
    "aws_organizations_",
    "aws_ssoadmin_",
    "aws_sns_",
    "aws_lambda_",
    "aws_cloudwatch_event_",
    "aws_scheduler_",
]


def _strip_comments(text: str) -> str:
    return "\n".join(re.sub(r"\s*#.*$", "", line) for line in text.splitlines())


def _tf(name: str) -> str:
    return _strip_comments((DEV / name).read_text(encoding="utf-8"))


def _all_tf() -> str:
    return "\n".join(_tf(p.name) for p in sorted(DEV.glob("*.tf")))


def _block(text: str, header: str) -> str:
    """The first block starting with `header`, up to its balanced closing brace.

    Interpolations such as "${path.module}" are skipped: their braces are not blocks.
    """
    start = text.index(header)
    opening = re.compile(r"(?<!\$)\{").search(text, start)
    assert opening, f"no block after {header}"
    depth = 0
    i = opening.start()
    while i < len(text):
        if text.startswith("${", i):
            i = text.index("}", i) + 1
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise AssertionError(f"unbalanced block {header}")


def _setting(block: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$", block, re.MULTILINE)
    assert match, f"{key} is not set"
    return match.group(1)


def _render(template: str, variables: dict[str, str]) -> str:
    """templatefile() semantics: ${name} is a variable; $${...} is a literal ${...}."""
    names = set(re.findall(r"(?<!\$)\$\{([A-Za-z_]+)\}", template))
    assert names <= set(variables), f"unknown template variables: {names - set(variables)}"
    assert "%{" not in template, "template directives are not used"
    out = re.sub(r"(?<!\$)\$\{([A-Za-z_]+)\}", lambda m: variables[m.group(1)], template)
    return out.replace("$${", "${")


# --- Resources and network ------------------------------------------------------------------


@pytest.mark.parametrize("resource_type", FORBIDDEN_RESOURCE_TYPES)
def test_no_forbidden_resource_type(resource_type):
    pattern = rf'(resource|data)\s+"{re.escape(resource_type)}'
    assert not re.search(pattern, _all_tf()), f"{resource_type} is forbidden"


def test_exactly_one_instance_and_it_is_the_workload():
    assert re.findall(r'resource\s+"aws_instance"\s+"(\w+)"', _all_tf()) == ["workload"]


def test_no_port_22_anywhere():
    text = _all_tf()
    for key in ("from_port", "to_port", "port"):
        assert not re.search(rf"\b{key}\s*=\s*22\b", text), f"{key} = 22 found"


def test_the_only_ingress_is_the_app_port_from_the_operator():
    text = _all_tf()
    ingress = re.findall(r'resource\s+"aws_vpc_security_group_ingress_rule"\s+"(\w+)"', text)
    assert ingress == ["app_from_operator"]
    rule = _block(text, 'resource "aws_vpc_security_group_ingress_rule" "app_from_operator"')
    assert _setting(rule, "cidr_ipv4") == "var.operator_cidr"
    assert _setting(rule, "from_port") == "var.app_port"
    assert _setting(rule, "to_port") == "var.app_port"
    assert "ingress {" not in text and "ingress=" not in text.replace(" ", "")


def test_the_only_egress_is_https():
    text = _all_tf()
    egress = re.findall(r'resource\s+"aws_vpc_security_group_egress_rule"\s+"(\w+)"', text)
    assert egress == ["https_out"]
    rule = _block(text, 'resource "aws_vpc_security_group_egress_rule" "https_out"')
    assert _setting(rule, "from_port") == "443"
    assert _setting(rule, "to_port") == "443"
    assert _setting(rule, "ip_protocol") == '"tcp"'
    assert "egress {" not in text


def test_default_security_group_is_managed_without_rules():
    block = _block(_all_tf(), 'resource "aws_default_security_group" "main"')
    assert "ingress" not in block and "egress" not in block


def test_operator_cidr_must_be_a_single_ipv4_address():
    block = _block(_tf("variables.tf"), 'variable "operator_cidr"')
    assert "default" not in block, "operator_cidr must have no default"
    assert "/32$" in block and "cidrhost" in block


def test_subnet_does_not_auto_assign_public_ips():
    block = _block(_all_tf(), 'resource "aws_subnet" "public"')
    assert _setting(block, "map_public_ip_on_launch") == "false"


# --- The instance ---------------------------------------------------------------------------


@pytest.fixture
def instance() -> str:
    return _block(_tf("compute.tf"), 'resource "aws_instance" "workload"')


def test_instance_shape_and_credits(instance):
    assert _setting(instance, "instance_type") == '"t3.micro"'
    assert _setting(_block(instance, "credit_specification"), "cpu_credits") == '"standard"'
    assert _setting(instance, "monitoring") == "false"


def test_instance_requires_imdsv2(instance):
    assert _setting(_block(instance, "metadata_options"), "http_tokens") == '"required"'


def test_root_volume_is_encrypted_gp3_and_deleted_with_the_instance(instance):
    root = _block(instance, "root_block_device")
    assert _setting(root, "volume_type") == '"gp3"'
    assert _setting(root, "encrypted") == "true"
    assert _setting(root, "delete_on_termination") == "true"
    assert "kms_key_id" not in root, "no customer-managed KMS key (forbidden)"
    assert "ebs_block_device" not in instance, "no extra volumes that could survive"


def test_os_shutdown_terminates_the_instance(instance):
    assert _setting(instance, "instance_initiated_shutdown_behavior") == '"terminate"'
    assert _setting(instance, "disable_api_termination") == "false"


def test_no_ssh_key_and_a_public_address_without_eip(instance):
    assert "key_name" not in instance
    assert _setting(instance, "associate_public_ip_address") == "true"


def test_user_data_change_replaces_the_instance(instance):
    assert _setting(instance, "user_data_replace_on_change") == "true"


def test_instance_is_tagged_for_monitoring(instance):
    assert '"cloudops-sentinel:monitor" = "true"' in instance


def test_safety_timer_has_bounds_and_a_240_minute_default():
    block = _block(_tf("variables.tf"), 'variable "safety_timer_minutes"')
    assert _setting(block, "default") == "240"
    assert ">= 15" in block and "<= 480" in block


def test_default_tags_are_set():
    providers = _tf("providers.tf")
    for tag in ('Project     = "cloudops-sentinel"', "Environment", 'ManagedBy   = "terraform"'):
        assert tag in providers


# --- IAM: the instance role -----------------------------------------------------------------


def test_instance_role_cannot_create_log_groups_or_use_wildcard_actions():
    iam = _tf("iam.tf")
    assert "logs:CreateLogGroup" not in iam
    assert "logs:PutRetentionPolicy" not in iam
    assert "CloudWatchAgentServerPolicy" not in iam, "use the scoped inline policy (D6)"
    for action in re.findall(r'"([a-z0-9-]+:[A-Za-z*]+)"', iam):
        assert "*" not in action, f"wildcard action {action}"


def test_instance_role_metrics_are_limited_to_the_agent_namespace():
    assert '"cloudwatch:namespace" = "CWAgent"' in _tf("iam.tf")


def test_instance_role_attaches_only_the_ssm_core_policy():
    attached = re.findall(r'policy_arn\s*=\s*"([^"]+)"', _tf("iam.tf"))
    assert attached == ["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"]


def test_terraform_never_manages_the_operator_or_sentinel_policies():
    text = _all_tf()
    assert "operator-terraform.json" not in text
    assert "sentinel-readonly.json" not in text, "the read-only role is a later PR (D10)"


# --- Logs and alarm -------------------------------------------------------------------------


def test_every_log_group_has_a_retention():
    text = _all_tf()
    groups = re.findall(r'resource\s+"aws_cloudwatch_log_group"\s+"(\w+)"', text)
    assert groups == ["access"]
    block = _block(text, 'resource "aws_cloudwatch_log_group" "access"')
    assert _setting(block, "retention_in_days") == "var.log_retention_days"
    variable = _block(_tf("variables.tf"), 'variable "log_retention_days"')
    assert _setting(variable, "default") == "3"


def test_one_cpu_alarm_named_for_sentinel_without_actions():
    text = _all_tf()
    assert re.findall(r'resource\s+"aws_cloudwatch_metric_alarm"\s+"(\w+)"', text) == ["cpu_high"]
    alarm = _block(text, 'resource "aws_cloudwatch_metric_alarm" "cpu_high"')
    assert _setting(alarm, "alarm_name") == '"${local.name}-cpu-high"'
    # local.name starts with cloudops-sentinel-, the prefix the read-only policy can read.
    assert re.search(
        r'^\s*name\s*=\s*"cloudops-sentinel-\$\{var\.environment\}"', _tf("main.tf"), re.M
    )
    assert _setting(alarm, "actions_enabled") == "false"
    assert "alarm_actions" not in alarm and "ok_actions" not in alarm
    assert int(_setting(alarm, "period")) >= 300, "basic monitoring: periods of 5 minutes"


# --- user_data and the safety timer ---------------------------------------------------------


def _user_data_template() -> str:
    return (TEMPLATES / "user_data.sh.tftpl").read_text(encoding="utf-8")


def _rendered_agent_config() -> dict:
    template = (TEMPLATES / "cloudwatch-agent.json.tftpl").read_text(encoding="utf-8")
    rendered = _render(
        template,
        {
            "log_group_name": "/cloudops-sentinel/dev/access",
            "access_log_path": "/var/log/cloudops-workload/access.log",
        },
    )
    return json.loads(rendered)


def _rendered_user_data() -> str:
    return _render(
        _user_data_template(),
        {
            "safety_timer_minutes": "240",
            "app_port": "8080",
            "access_log_path": "/var/log/cloudops-workload/access.log",
            "app_py": APP.read_text(encoding="utf-8"),
            "agent_config": json.dumps(_rendered_agent_config(), indent=2),
        },
    )


def test_user_data_template_uses_exactly_the_variables_compute_tf_passes():
    template_vars = set(re.findall(r"(?<!\$)\$\{([A-Za-z_]+)\}", _user_data_template()))
    call = _block(_tf("compute.tf"), "user_data = templatefile(")
    passed = set(re.findall(r"^\s{4}(\w+)\s+=", call, re.MULTILINE))
    assert (
        template_vars
        == passed
        == {
            "safety_timer_minutes",
            "app_port",
            "access_log_path",
            "app_py",
            "agent_config",
        }
    )


def test_safety_timer_is_installed_before_anything_that_can_fail():
    script = _user_data_template()
    timer = script.index("systemctl enable --now cloudops-safety-shutdown.timer")
    for later in ("set -euo pipefail", "dnf install", "useradd", "amazon-cloudwatch-agent-ctl"):
        assert timer < script.index(later), f"{later} runs before the timer is armed"
    assert "set -e" not in script[:timer], "a failure must not stop the script before the timer"


def test_safety_timer_powers_off_and_never_halts():
    lines = [line.strip() for line in _user_data_template().splitlines()]
    commands = [line for line in lines if not line.startswith("#")]
    assert "ExecStart=/usr/bin/systemctl poweroff" in commands
    assert "OnBootSec=${safety_timer_minutes}min" in commands
    # AWS: `halt` does not initiate a shutdown, so the instance would keep running and billing.
    assert not any(re.search(r"\bhalt\b", line) for line in commands)
    # Fallback when the timer cannot be enabled: a one-shot poweroff (-P), never a halt (-H).
    assert any('shutdown -P "+${safety_timer_minutes}"' in line for line in commands)


def test_safety_timer_is_labelled_untested():
    for path in (
        TEMPLATES / "user_data.sh.tftpl",
        DEV / "compute.tf",
        ROOT / "infra" / "README.md",
    ):
        assert "UNTESTED" in path.read_text(encoding="utf-8"), path.name


def test_rendered_user_data_fits_the_ec2_limit():
    # EC2 user data is limited to 16 KB before base64 encoding.
    assert len(_rendered_user_data().encode("utf-8")) < 16 * 1024


def test_app_cannot_end_its_heredoc_early():
    assert "PYEOF" not in APP.read_text(encoding="utf-8")
    assert "JSONEOF" not in json.dumps(_rendered_agent_config())


# --- CloudWatch agent: one metric, one dimension --------------------------------------------


def test_agent_config_is_valid_json_with_exactly_one_metric():
    config = _rendered_agent_config()
    metrics = config["metrics"]
    assert metrics["namespace"] == "CWAgent"
    assert list(metrics["metrics_collected"]) == ["mem"]
    assert metrics["metrics_collected"]["mem"]["measurement"] == ["mem_used_percent"]


def test_agent_metric_has_instance_id_as_its_only_dimension():
    config = _rendered_agent_config()
    assert config["metrics"]["append_dimensions"] == {"InstanceId": "${aws:InstanceId}"}
    assert config["agent"]["omit_hostname"] is True
    assert "aggregation_dimensions" not in config["metrics"]
    for section in config["metrics"]["metrics_collected"].values():
        assert "append_dimensions" not in section and "aggregation_dimensions" not in section


def test_agent_ships_one_log_file_to_the_terraform_log_group():
    config = _rendered_agent_config()
    files = config["logs"]["logs_collected"]["files"]["collect_list"]
    assert len(files) == 1
    entry = files[0]
    assert entry["log_group_name"] == "/cloudops-sentinel/dev/access"
    assert entry["file_path"] == "/var/log/cloudops-workload/access.log"
    # Terraform owns retention; the agent must not set it (nor create an unmanaged group).
    assert "retention_in_days" not in entry
    assert config["agent"]["usage_data"] is False


# --- The leftover check ---------------------------------------------------------------------

READ_ONLY_OPERATION = re.compile(r"^(describe|list|get)-[a-z-]+$")


def _aws_operations(script: str) -> list[tuple[str, str]]:
    """Every `check "<label>" <service> <operation>` and direct `aws_ro <service> <op>`."""
    ops = re.findall(r'^\S*check\s+"[^"]+"\s+(\S+)\s+(\S+)', script, re.MULTILINE)
    ops += re.findall(r"aws_ro\s+([a-z0-9-]+)\s+([a-z-]+)", script)
    return ops


def test_cost_check_uses_read_only_operations_only():
    script = COST_CHECK.read_text(encoding="utf-8")
    operations = _aws_operations(script)
    assert len(operations) >= 15
    for service, operation in operations:
        assert READ_ONLY_OPERATION.match(operation), f"{service} {operation} is not read-only"
    # Nothing calls the CLI outside the read-only wrapper (comments and messages aside).
    code = [line for line in script.splitlines() if not line.lstrip().startswith(("#", "echo"))]
    direct = [line for line in code if re.search(r"(?<![\w/-])aws\s", line)]
    assert direct == ['  AWS_PAGER="" aws --region "$REGION" --output text "$@"']


def test_cost_check_masks_the_account_id():
    script = COST_CHECK.read_text(encoding="utf-8")
    assert "****${account: -4}" in script
    assert "s/[0-9]{12}/" in script, "error messages are masked too"


def test_cost_check_treats_a_failed_call_as_an_error_not_as_clean():
    script = COST_CHECK.read_text(encoding="utf-8")
    assert "ERRORS=1" in script and "exit 2" in script
