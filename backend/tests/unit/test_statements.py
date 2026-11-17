"""Statement templates: what a fact says must match its data."""

from datetime import UTC, datetime, timedelta, timezone

from sentinel.detection.statements import hhmm


def test_hhmm_converts_to_utc_instead_of_relabelling():
    # 13:10 at +01:00 is 12:10 UTC. Seen on a real sync before the collector fix: a fact
    # said "since 13:10 UTC" while its window started at 12:10 UTC.
    local = datetime(2026, 11, 17, 13, 10, tzinfo=timezone(timedelta(hours=1)))
    assert hhmm(local) == "12:10 UTC"
    assert hhmm(datetime(2026, 11, 17, 12, 10, tzinfo=UTC)) == "12:10 UTC"
