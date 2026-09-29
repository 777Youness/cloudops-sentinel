"""Every scenario file must produce exactly the outcome it declares."""

from datetime import timedelta
from itertools import count

import pytest

from sentinel.collectors.simulated import SimulatedSource, load_scenarios
from sentinel.config import Settings
from sentinel.detection import engine

SCENARIOS = load_scenarios(Settings().scenarios_dir)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_scenario_expected_outcome(scenario, clock):
    now = clock.now()
    source = SimulatedSource([scenario], clock, region="eu-west-3")
    snapshot = source.collect(now - timedelta(hours=3), now)
    ids = count(1)
    result = engine.evaluate(snapshot, set(), now, lambda: f"INC-{next(ids):04d}")

    assert bool(result.opened) == scenario.expected.incident
    if scenario.expected.incident:
        [incident] = result.opened
        assert incident.rule_ids == scenario.expected.rules
        assert incident.severity == scenario.expected.severity


def test_at_least_one_scenario_exists():
    assert SCENARIOS
