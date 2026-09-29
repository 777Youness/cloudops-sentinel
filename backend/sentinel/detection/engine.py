"""The detection engine: observations + open incidents -> new incidents.

Pure: no I/O, no clock (time is passed in), no knowledge of AWS or HTTP.

Day 1 lifecycle (deliberately partial):
  - a triggered rule on a resource with no open incident opens a new incident;
  - a resource that already has an open incident is left unchanged (no duplicates).
Merging new facts into an open incident and resolving incidents arrive on Day 2.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sentinel.detection import rules, statements, thresholds
from sentinel.detection.severity import incident_severity
from sentinel.domain.incidents import (
    Fact,
    Incident,
    IncidentEvidence,
    KeySignal,
    TimelineEntry,
    TimeWindow,
)
from sentinel.domain.observations import MetricSeries, ObservationSnapshot, Resource


@dataclass
class EvaluationResult:
    opened: list[Incident] = field(default_factory=list)
    rule_results: list[rules.RuleResult] = field(default_factory=list)
    resources_evaluated: int = 0
    rules_evaluated: int = len(rules.RULE_IDS)


def _find_series(
    snapshot: ObservationSnapshot, resource_id: str, signal: str
) -> MetricSeries | None:
    for s in snapshot.series:
        if s.resource_id == resource_id and s.signal == signal:
            return s
    return None


def _evidence_hash(facts: list[Fact], evidence: IncidentEvidence) -> str:
    payload = "".join(f.model_dump_json() for f in facts) + evidence.model_dump_json()
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _open_cpu_incident(
    resource: Resource,
    series: MetricSeries,
    result: rules.RuleResult,
    now: datetime,
    incident_id: str,
) -> Incident:
    assert result.triggered and result.breach_start and result.duration and result.peak
    fact = Fact(
        id="F1",
        kind="threshold_breach",
        statement=statements.cpu_saturation_fact(
            thresholds.CPU_SAT_THRESHOLD_PERCENT, result.duration, result.peak, result.breach_start
        ),
        source=series.source,
        resource_id=resource.id,
        observed_at=result.breach_end or now,
        window=TimeWindow(start=result.breach_start, end=result.breach_end or now),
        rule_id=result.rule_id,
        signal="cpu_utilization",
        value=result.peak,
        threshold=thresholds.CPU_SAT_THRESHOLD_PERCENT,
        unit="percent",
    )
    lookback_start = result.breach_start - thresholds.EVIDENCE_LOOKBACK
    evidence = IncidentEvidence(
        series=[
            series.model_copy(
                update={"points": [p for p in series.points if p.t >= lookback_start]}
            )
        ]
    )
    rule_ids = [result.rule_id]
    severity = incident_severity(rule_ids)
    return Incident(
        id=incident_id,
        fingerprint=resource.id,
        title=statements.cpu_saturation_title(resource.name),
        severity=severity,
        status="open",
        resource_id=resource.id,
        resource_name=resource.name,
        region=resource.region,
        data_origin=resource.data_origin,
        rule_ids=rule_ids,
        first_detected_at=now,
        last_updated_at=now,
        key_signals=[KeySignal(signal="cpu_utilization", value=result.latest or 0, unit="percent")],
        facts=[fact],
        timeline=[
            TimelineEntry(
                at=result.breach_start,
                kind="breach_start",
                label=statements.breach_start_label(thresholds.CPU_SAT_THRESHOLD_PERCENT),
                fact_id="F1",
            ),
            TimelineEntry(
                at=now,
                kind="incident_opened",
                label=statements.incident_opened_label(rule_ids, severity),
            ),
        ],
        evidence=evidence,
        evidence_hash=_evidence_hash([fact], evidence),
    )


def evaluate(
    snapshot: ObservationSnapshot,
    open_fingerprints: set[str],
    now: datetime,
    allocate_id: Callable[[], str],
) -> EvaluationResult:
    result = EvaluationResult(resources_evaluated=len(snapshot.resources))
    for resource in snapshot.resources:
        series = _find_series(snapshot, resource.id, "cpu_utilization")
        cpu = rules.cpu_saturation(series, resource.id)
        result.rule_results.append(cpu)
        if not cpu.triggered or resource.id in open_fingerprints:
            continue
        assert series is not None  # a triggered rule implies data
        result.opened.append(_open_cpu_incident(resource, series, cpu, now, allocate_id()))
    return result
