"""Discovery: only instances tagged cloudops-sentinel:monitor=true, never terminated."""

from sentinel.collectors.aws.ec2 import add_credit_modes, discover_instances
from tests.aws.conftest import INSTANCE_ID, REGION, credit_specs, describe_instances, instance

DISCOVERY_PARAMS = {
    "Filters": [
        {"Name": "tag:cloudops-sentinel:monitor", "Values": ["true"]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
    ]
}


def test_discovery_filters_on_the_monitor_tag_and_live_states(stubs):
    stubs.ec2.add_response("describe_instances", describe_instances(instance()), DISCOVERY_PARAMS)
    [resource] = discover_instances(stubs.clients.ec2, REGION)
    assert resource.id == INSTANCE_ID
    assert resource.name == "cloudops-dev"
    assert resource.state == "running"
    assert resource.instance_type == "t3.micro"
    assert resource.region == REGION
    assert resource.data_origin == "aws"
    assert resource.tags["Project"] == "cloudops-sentinel"


def test_no_monitored_instance_is_an_empty_list_not_an_error(stubs):
    stubs.ec2.add_response("describe_instances", describe_instances(), DISCOVERY_PARAMS)
    assert discover_instances(stubs.clients.ec2, REGION) == []


def test_instance_without_name_tag_uses_its_id(stubs):
    raw = instance()
    raw["Tags"] = [{"Key": "cloudops-sentinel:monitor", "Value": "true"}]
    stubs.ec2.add_response("describe_instances", describe_instances(raw), DISCOVERY_PARAMS)
    assert discover_instances(stubs.clients.ec2, REGION)[0].name == INSTANCE_ID


def test_credit_mode_comes_from_the_credit_specification(stubs):
    stubs.ec2.add_response("describe_instances", describe_instances(instance()), DISCOVERY_PARAMS)
    stubs.ec2.add_response(
        "describe_instance_credit_specifications",
        credit_specs("standard"),
        {"InstanceIds": [INSTANCE_ID]},
    )
    resources = discover_instances(stubs.clients.ec2, REGION)
    assert add_credit_modes(stubs.clients.ec2, resources) is None
    assert resources[0].credit_mode == "standard"


def test_credit_specification_failure_is_reported_not_hidden(stubs):
    stubs.ec2.add_response("describe_instances", describe_instances(instance()), DISCOVERY_PARAMS)
    stubs.ec2.add_client_error(
        "describe_instance_credit_specifications", service_error_code="UnauthorizedOperation"
    )
    resources = discover_instances(stubs.clients.ec2, REGION)
    error = add_credit_modes(stubs.clients.ec2, resources)
    assert error is not None and error.code == "access_denied"
    assert resources[0].credit_mode is None


def test_non_burstable_instances_need_no_credit_call(stubs):
    stubs.ec2.add_response(
        "describe_instances",
        describe_instances(instance(instance_type="m5.large")),
        DISCOVERY_PARAMS,
    )
    resources = discover_instances(stubs.clients.ec2, REGION)
    assert add_credit_modes(stubs.clients.ec2, resources) is None  # no stubbed call needed
