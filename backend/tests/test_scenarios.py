"""Every scenario file must produce exactly the outcome it declares, phase by phase.

Each phase is one real sync (SyncService + SQLite in memory), so this also exercises the
incident lifecycle end to end: open, update, resolve, reopen.
"""

from datetime import timedelta

import pytest

from sentinel.collectors.simulated import SimulatedSource, load_scenarios
from sentinel.config import Settings
from sentinel.detection import rules
from sentinel.domain.observations import MetricSeries, SignalName
from sentinel.services.sync import SyncService
from sentinel.store.sqlite import SqliteStore

SCENARIOS = load_scenarios(Settings().scenarios_dir)

OUTCOME_COUNTERS = {
    "opened": "incidents_opened",
    "updated": "incidents_updated",
    "resolved": "incidents_resolved",
}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_scenario_expected_outcome(scenario, clock):
    store = SqliteStore(":memory:")
    source = SimulatedSource([scenario], clock, region="eu-west-3")
    sync = SyncService(source, store, clock, window=timedelta(hours=3))

    for index in range(max(1, len(scenario.phases))):
        expected = scenario.phase(index).expected
        run = sync.run()
        assert run.status == "success"
        where = f"phase {index + 1}"

        if expected.outcome is not None:
            counts = {name: getattr(run, field) for name, field in OUTCOME_COUNTERS.items()}
            wanted = {name: int(name == expected.outcome) for name in OUTCOME_COUNTERS}
            assert counts == wanted, where

        open_incidents = store.open_incidents()
        assert bool(open_incidents) == expected.incident, where
        if expected.incident:
            [incident] = open_incidents
            assert incident.rule_ids == expected.rules, where
            assert incident.severity == expected.severity, where

        snapshot = store.latest_snapshot()
        assert snapshot is not None
        [resource] = snapshot.resources
        series: dict[SignalName, MetricSeries] = {s.signal: s for s in snapshot.series}
        reasons = {r.rule_id: r.reason for r in rules.evaluate_resource(resource, series)}
        for rule_id, reason in expected.reasons.items():
            assert reasons[rule_id] == reason, f"{where}: {rule_id}"

        clock.advance(timedelta(minutes=1))


def test_at_least_one_scenario_exists():
    assert SCENARIOS


def test_lifecycle_is_covered_by_scenarios():
    outcomes = {p.expected.outcome for s in SCENARIOS for p in s.phases}
    assert {"opened", "updated", "resolved", "unchanged"} <= outcomes
