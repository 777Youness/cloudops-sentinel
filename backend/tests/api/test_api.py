from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentinel.collectors.simulated import load_scenarios
from sentinel.config import Settings
from sentinel.main import create_app

# A single CPU-saturation scenario keeps these API tests independent of the scenario set.
ONE_SCENARIO_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "scenarios"


@pytest.fixture
def client(clock):
    return TestClient(
        create_app(
            Settings(mode="local", scenarios_dir=ONE_SCENARIO_DIR, db_path=":memory:"), clock
        )
    )


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_system_before_any_sync(client):
    body = client.get("/api/v1/system").json()
    assert body["mode"] == "local"
    assert body["last_sync"] is None
    assert body["llm"]["configured"] is False


def test_incidents_empty_before_sync(client):
    assert client.get("/api/v1/incidents").json() == {"items": [], "total": 0}


def test_sync_opens_one_incident(client):
    run = client.post("/api/v1/sync").json()
    assert run["status"] == "success"
    assert run["incidents_opened"] == 1
    body = client.get("/api/v1/incidents").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["severity"] == "medium"
    assert item["data_origin"] == "simulated"
    assert item["investigation_status"] == "not_run"


def test_second_sync_does_not_duplicate(client):
    client.post("/api/v1/sync")
    run = client.post("/api/v1/sync").json()
    assert run["incidents_opened"] == 0
    assert client.get("/api/v1/incidents").json()["total"] == 1


def test_timestamps_are_utc_with_z(client):
    client.post("/api/v1/sync")
    item = client.get("/api/v1/incidents").json()["items"][0]
    assert item["first_detected_at"].endswith("Z")


def test_concurrent_sync_returns_409(client):
    sync_service = client.app.state.container.sync
    sync_service._lock.acquire()  # simulate a sync already running
    try:
        response = client.post("/api/v1/sync")
    finally:
        sync_service._lock.release()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SYNC_IN_PROGRESS"


def test_invalid_status_filter_uses_error_envelope(client):
    response = client.get("/api/v1/incidents?status=broken")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_failing_collector_is_reported_not_raised(client):
    def broken(*_args, **_kwargs):
        raise ConnectionError("simulated source unreachable")

    client.app.state.container.sync._source.collect = broken
    run = client.post("/api/v1/sync").json()
    assert run["status"] == "failed"
    assert run["collectors"][0]["state"] == "failed"
    assert run["collectors"][0]["error"]["code"] == "ConnectionError"


def test_aws_mode_fails_honestly():
    with pytest.raises(RuntimeError, match="not implemented"):
        create_app(Settings(mode="aws"))


def test_full_scenario_set_opens_one_incident_per_incident_scenario(clock):
    settings = Settings(mode="local", db_path=":memory:")
    client = TestClient(create_app(settings, clock))
    scenarios = load_scenarios(settings.scenarios_dir)
    expected = [s for s in scenarios if s.phase(0).expected.incident]
    run = client.post("/api/v1/sync").json()
    assert run["incidents_opened"] == len(expected)
    items = client.get("/api/v1/incidents").json()["items"]
    # sorted by severity: the critical status-check incident comes first
    assert items[0]["severity"] == "critical"


def test_incidents_survive_a_restart(clock, tmp_path):
    settings = Settings(scenarios_dir=ONE_SCENARIO_DIR, db_path=str(tmp_path / "sentinel.db"))
    first = TestClient(create_app(settings, clock))
    first.post("/api/v1/sync")
    first.app.state.container.store.close()

    second = TestClient(create_app(settings, clock))
    assert second.get("/api/v1/incidents").json()["total"] == 1
    assert second.get("/api/v1/system").json()["last_sync"]["id"] == "SYNC-0001"
    second.app.state.container.store.close()


def test_default_database_is_one_file_per_mode():
    assert Settings(mode="local").resolved_db_path().endswith("sentinel-local.db")
    assert Settings(mode="aws").resolved_db_path().endswith("sentinel-aws.db")


# --- incident detail ---------------------------------------------------------------------


def test_incident_detail_returns_everything_stored(client):
    client.post("/api/v1/sync")
    [summary] = client.get("/api/v1/incidents").json()["items"]
    body = client.get(f"/api/v1/incidents/{summary['id']}").json()
    assert body["id"] == summary["id"]
    assert body["rule_ids"] == ["R-CPU-SAT"]
    assert body["evidence_hash"].startswith("sha256:")
    assert body["facts"][0]["id"] == "F1"
    assert body["facts"][0]["kind"] == "threshold_breach"
    assert {e["kind"] for e in body["timeline"]} >= {"breach_start", "incident_opened"}
    assert {s["signal"] for s in body["evidence"]["series"]} >= {"cpu_utilization"}
    # the stored incident, verbatim: what the API returns is what detection produced
    stored = client.app.state.container.incidents.get(summary["id"])
    assert body == stored.model_dump(mode="json")


def test_unknown_incident_is_404_with_envelope(client):
    response = client.get("/api/v1/incidents/INC-9999")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert "INC-9999" in error["message"]


def test_incident_list_is_sorted_by_severity_then_recency(clock):
    settings = Settings(mode="local", db_path=":memory:")
    client = TestClient(create_app(settings, clock))
    client.post("/api/v1/sync")
    severities = [i["severity"] for i in client.get("/api/v1/incidents").json()["items"]]
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    assert severities == sorted(severities, key=order.get, reverse=True)


# --- overview ----------------------------------------------------------------------------


def test_overview_before_any_sync(client):
    body = client.get("/api/v1/overview").json()
    assert body["last_sync"] is None
    assert body["data_as_of"] is None
    assert body["data_origin"] is None
    assert body["open_total"] == 0
    assert body["resources"] == []


def test_overview_after_sync(clock):
    settings = Settings(mode="local", db_path=":memory:")
    client = TestClient(create_app(settings, clock))
    client.post("/api/v1/sync")
    body = client.get("/api/v1/overview").json()
    open_items = client.get("/api/v1/incidents").json()["items"]

    assert body["data_origin"] == "simulated"
    assert body["data_as_of"] == body["last_sync"]["finished_at"]
    assert body["open_total"] == len(open_items)
    assert sum(body["open_by_severity"].values()) == len(open_items)
    assert [i["id"] for i in body["top_open_incidents"]] == [i["id"] for i in open_items[:5]]

    health = {r["resource_id"]: r for r in body["resources"]}
    assert health["sim-healthy"]["health"] == "ok"
    assert health["sim-status-check-failure"]["health"] == "crit"
    assert health["sim-memory-pressure"]["health"] == "warn"
    # the CPU scenario has no memory agent: reported as missing, never as 0 or healthy-by-omission
    assert health["sim-cpu-saturation"]["signals_missing"] == ["memory_used"]


def test_failed_sync_does_not_refresh_data_as_of(clock):
    settings = Settings(mode="local", scenarios_dir=ONE_SCENARIO_DIR, db_path=":memory:")
    client = TestClient(create_app(settings, clock))
    client.post("/api/v1/sync")
    first = client.get("/api/v1/system").json()["data_as_of"]

    def broken(*_):
        raise ConnectionError("source down")

    clock.advance(timedelta(minutes=20))
    client.app.state.container.sync._source.collect = broken
    assert client.post("/api/v1/sync").json()["status"] == "failed"
    system = client.get("/api/v1/system").json()
    assert system["last_sync"]["status"] == "failed"
    assert system["data_as_of"] == first  # the data is still the old data
    assert client.get("/api/v1/overview").json()["data_as_of"] == first
