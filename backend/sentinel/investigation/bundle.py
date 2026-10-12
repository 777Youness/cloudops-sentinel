"""The evidence bundle: everything the LLM may use, built from one stored incident.

Only facts, the timeline and the incident's identity go in. No raw time series: the model
must reason from facts it can cite, not from numbers it read off a series. Severity is
included as read-only context; the model cannot return it (see domain/investigation.py).

Pure: no I/O, no clock.
"""

import json
from typing import Any

from sentinel.domain.incidents import Incident

# Free text that did not come from a code template (deployment labels today, log samples
# from Day 5) is cut to this length: it is data, and data is kept small.
MAX_TEXT = 300


def _clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def build_bundle(incident: Incident) -> dict[str, Any]:
    return {
        "incident": {
            "id": incident.id,
            "title": incident.title,
            "severity": incident.severity,
            "status": incident.status,
            "resource_id": incident.resource_id,
            "resource_name": incident.resource_name,
            "region": incident.region,
            "data_origin": incident.data_origin,
            "rule_ids": incident.rule_ids,
            "first_detected_at": incident.first_detected_at.isoformat(),
            "last_updated_at": incident.last_updated_at.isoformat(),
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        },
        "facts": [
            {
                "id": f.id,
                "kind": f.kind,
                "statement": _clip(f.statement),
                "observed_at": f.observed_at.isoformat(),
                "window": (
                    {"start": f.window.start.isoformat(), "end": f.window.end.isoformat()}
                    if f.window
                    else None
                ),
                "rule_id": f.rule_id,
                "signal": f.signal,
                "value": f.value,
                "threshold": f.threshold,
                "baseline": f.baseline,
                "unit": f.unit,
            }
            for f in incident.facts
        ],
        "timeline": [
            {"at": e.at.isoformat(), "kind": e.kind, "label": _clip(e.label), "fact_id": e.fact_id}
            for e in incident.timeline
        ],
    }


def bundle_json(bundle: dict[str, Any]) -> str:
    """Deterministic serialization: the same incident always produces the same prompt."""
    return json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False)


def fact_ids(bundle: dict[str, Any]) -> set[str]:
    return {f["id"] for f in bundle["facts"]}
