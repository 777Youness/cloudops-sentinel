import pytest
from fastapi.testclient import TestClient

from sentinel.config import Settings
from sentinel.main import create_app


@pytest.fixture
def client(clock):
    return TestClient(create_app(Settings(mode="local"), clock))


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
