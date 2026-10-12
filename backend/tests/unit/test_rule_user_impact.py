"""C-USER-IMPACT: R-LAT and R-5XX both active on the same resource."""

from sentinel.detection.rules import RuleResult, user_impact


def _r(rule_id, triggered):
    return RuleResult(rule_id, "r-1", triggered=triggered)


def test_triggers_when_latency_and_errors_are_both_active():
    assert user_impact([_r("R-LAT", True), _r("R-5XX", True)], "r-1").triggered


def test_does_not_trigger_with_only_one_of_them():
    assert not user_impact([_r("R-LAT", True), _r("R-5XX", False)], "r-1").triggered
    assert not user_impact([_r("R-LAT", False), _r("R-5XX", True)], "r-1").triggered


def test_other_rules_do_not_count():
    assert not user_impact([_r("R-CPU-SAT", True), _r("R-MEM", True)], "r-1").triggered
