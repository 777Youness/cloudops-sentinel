"""The severity matrix decides severity; nothing else does."""

import pytest

from sentinel.detection.rules import RuleResult
from sentinel.detection.severity import incident_severity


def _r(rule_id, lower_tier=False, triggered=True):
    return RuleResult(rule_id, "r-1", triggered=triggered, lower_tier=lower_tier)


def test_highest_severity_wins():
    assert incident_severity([_r("R-CPU-SAT"), _r("R-STATUS")]) == "critical"


def test_5xx_full_tier_is_high_and_lower_tier_is_medium():
    assert incident_severity([_r("R-5XX")]) == "high"
    assert incident_severity([_r("R-5XX", lower_tier=True)]) == "medium"


def test_user_impact_raises_two_medium_rules_to_high():
    results = [_r("R-5XX", lower_tier=True), _r("R-LAT"), _r("C-USER-IMPACT")]
    assert incident_severity(results) == "high"


def test_rules_that_did_not_trigger_are_ignored():
    assert incident_severity([_r("R-MEM"), _r("R-STATUS", triggered=False)]) == "medium"


def test_no_triggered_rule_is_an_error():
    with pytest.raises(ValueError):
        incident_severity([_r("R-MEM", triggered=False)])
