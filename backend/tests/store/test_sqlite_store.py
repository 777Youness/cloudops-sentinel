"""SqliteStore: the storage contract, transactions, persistence and schema versioning."""

import sqlite3
from contextlib import closing
from datetime import timedelta

import pytest

from sentinel.detection import engine
from sentinel.domain.observations import ObservationSnapshot, Resource
from sentinel.domain.system import SyncRun
from sentinel.store.sqlite import SCHEMA_VERSION, SqliteStore
from tests.conftest import NOW, make_series


def _incident(incident_id="INC-0001"):
    resource = Resource(
        id="r-1",
        name="api-01",
        region="eu-west-3",
        state="running",
        instance_type="t3.micro",
        data_origin="simulated",
    )
    snapshot = ObservationSnapshot(
        collected_at=NOW,
        window_start=NOW - timedelta(hours=3),
        window_end=NOW,
        data_origin="simulated",
        resources=[resource],
        series=[make_series([40.0] * 90 + [97.0] * 20)],
    )
    [incident] = engine.evaluate(snapshot, [], NOW, lambda: incident_id).opened
    return incident


def _run(run_id, minutes=0):
    return SyncRun(
        id=run_id,
        started_at=NOW + timedelta(minutes=minutes),
        finished_at=NOW + timedelta(minutes=minutes),
        status="success",
        collectors=[],
        resources_evaluated=1,
        rules_evaluated=7,
        incidents_opened=0,
        incidents_updated=0,
        incidents_resolved=0,
    )


@pytest.fixture
def store():
    return SqliteStore(":memory:")


def test_ids_are_sequential(store):
    assert [store.next_incident_id() for _ in range(2)] == ["INC-0001", "INC-0002"]
    assert store.next_sync_id() == "SYNC-0001"


def test_incident_round_trip(store):
    incident = _incident()
    store.add_incident(incident)
    assert store.get_incident("INC-0001") == incident
    assert store.get_incident("INC-9999") is None


def test_update_changes_status_and_open_list(store):
    incident = _incident()
    store.add_incident(incident)
    assert [i.id for i in store.open_incidents()] == ["INC-0001"]
    store.update_incident(incident.model_copy(update={"status": "resolved", "resolved_at": NOW}))
    assert store.open_incidents() == []
    assert [i.id for i in store.list_incidents("resolved")] == ["INC-0001"]
    assert len(store.list_incidents()) == 1


def test_updating_an_unknown_incident_fails(store):
    with pytest.raises(KeyError):
        store.update_incident(_incident())


def test_last_sync_is_the_most_recent(store):
    assert store.last_sync() is None
    store.record_sync(_run("SYNC-0001", minutes=0))
    store.record_sync(_run("SYNC-0002", minutes=5))
    assert store.last_sync().id == "SYNC-0002"


def test_snapshot_round_trip(store):
    assert store.latest_snapshot() is None
    snapshot = ObservationSnapshot(
        collected_at=NOW,
        window_start=NOW,
        window_end=NOW,
        data_origin="simulated",
        resources=[],
        series=[],
    )
    store.save_snapshot(snapshot)
    store.save_snapshot(snapshot)  # only the latest is kept
    assert store.latest_snapshot() == snapshot


def test_transaction_rolls_back_everything_on_error(store):
    with pytest.raises(RuntimeError), store.transaction():
        store.add_incident(_incident(store.next_incident_id()))
        store.record_sync(_run(store.next_sync_id()))
        raise RuntimeError("crash in the middle of a sync")
    assert store.list_incidents() == []
    assert store.last_sync() is None
    assert store.next_incident_id() == "INC-0001"  # the id counter was rolled back too


def test_data_survives_reopening_the_file(tmp_path):
    path = tmp_path / "sentinel.db"
    first = SqliteStore(path)
    first.add_incident(_incident(first.next_incident_id()))
    first.close()

    second = SqliteStore(path)
    assert [i.id for i in second.list_incidents()] == ["INC-0001"]
    assert second.next_incident_id() == "INC-0002"


def test_schema_version_is_recorded(tmp_path):
    path = tmp_path / "sentinel.db"
    SqliteStore(path).close()
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / "sentinel.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError, match="newer than this code"):
        SqliteStore(path)


def test_last_successful_sync_skips_failed_runs(store):
    assert store.last_successful_sync() is None
    store.record_sync(_run("SYNC-0001", minutes=0))
    store.record_sync(_run("SYNC-0002", minutes=5).model_copy(update={"status": "failed"}))
    assert store.last_sync().id == "SYNC-0002"
    assert store.last_successful_sync().id == "SYNC-0001"
