"""The detection engine: observations + open incidents -> new incidents.

Pure: no I/O, no clock (time is passed in), no knowledge of AWS or HTTP.

One incident per resource. All rules that trigger on a resource in the same evaluation go
into the same incident; its severity is the highest one in the severity matrix.

Lifecycle so far (deliberately partial):
  - triggered rules on a resource with no open incident open a new incident;
  - a resource that already has an open incident is left unchanged (no duplicates).
Merging new facts into an open incident and resolving incidents arrive in milestone 2b.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sentinel.detection import rules, statements, thresholds
from sentinel.detection.severity import incident_severity, rule_severity
from sentinel.domain.incidents import (
    SEVERITY_ORDER,
    Fact,
    Incident,
    IncidentEvidence,
    KeySignal,
    TimelineEntry,
    TimeWindow,
)
from sentinel.domain.observations import MetricSeries, ObservationSnapshot, Resource, SignalName

# Rules that could not be evaluated become data_gap facts: "we could not check this".
GAP_REASONS = ("insufficient_data", "insufficient_traffic")


@dataclass
class EvaluationResult:
    opened: list[Incident] = field(default_factory=list)
    rule_results: list[rules.RuleResult] = field(default_factory=list)
    resources_evaluated: int = 0
    rules_evaluated: int = len(rules.RULE_IDS)


def _series_for(snapshot: ObservationSnapshot, resource_id: str) -> dict[SignalName, MetricSeries]:
    return {s.signal: s for s in snapshot.series if s.resource_id == resource_id}


def _evidence_hash(facts: list[Fact], evidence: IncidentEvidence) -> str:
    payload = "".join(f.model_dump_json() for f in facts) + evidence.model_dump_json()
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def _primary(triggered: list[rules.RuleResult]) -> rules.RuleResult:
    """The rule that names the incident: highest severity; the derived rule wins ties,
    because it describes the situation better than either of its parts."""
    return max(
        triggered,
        key=lambda r: (SEVERITY_ORDER[rule_severity(r)], r.rule_id.startswith("C-")),
    )


def _build_facts(
    resource: Resource,
    series: dict[SignalName, MetricSeries],
    results: list[rules.RuleResult],
    snapshot: ObservationSnapshot,
) -> tuple[list[Fact], list[TimelineEntry]]:
    """Facts in a fixed order: breaches, then what was checked and normal, then data gaps."""
    facts: list[Fact] = []
    timeline: list[TimelineEntry] = []

    def next_id() -> str:
        return f"F{len(facts) + 1}"

    for r in results:
        if not r.triggered or r.signal is None:
            continue  # C-USER-IMPACT has no observation of its own: its parts are the facts
        assert r.breach_start and r.breach_end
        s = series[r.signal]
        fact = Fact(
            id=next_id(),
            kind="baseline_deviation" if r.baseline is not None else "threshold_breach",
            statement=statements.breach_fact(r, s.unit),
            source=s.source,
            resource_id=resource.id,
            observed_at=r.breach_end,
            window=TimeWindow(start=r.breach_start, end=r.breach_end),
            rule_id=r.rule_id,
            signal=r.signal,
            value=r.peak,
            baseline=r.baseline,
            threshold=r.threshold,
            unit=s.unit,
        )
        facts.append(fact)
        timeline.append(
            TimelineEntry(
                at=r.breach_start,
                kind="breach_start",
                label=statements.breach_start_label(r, s.unit),
                fact_id=fact.id,
            )
        )

    for r in results:
        if r.reason != "below_threshold" or r.signal is None:
            continue
        s = series[r.signal]
        facts.append(
            Fact(
                id=next_id(),
                kind="within_normal",
                statement=statements.within_normal_fact(r, s.unit),
                source=s.source,
                resource_id=resource.id,
                observed_at=s.points[-1].t,
                rule_id=r.rule_id,
                signal=r.signal,
                value=r.latest,
                threshold=r.threshold,
                unit=s.unit,
            )
        )

    for r in results:
        if r.reason not in GAP_REASONS:
            continue
        facts.append(
            Fact(
                id=next_id(),
                kind="data_gap",
                statement=statements.data_gap_fact(r),
                source="detection",
                resource_id=resource.id,
                observed_at=snapshot.window_end,
                window=TimeWindow(start=snapshot.window_start, end=snapshot.window_end),
                rule_id=r.rule_id,
                signal=r.signal,
            )
        )

    timeline.sort(key=lambda e: e.at)
    return facts, timeline


def _open_incident(
    resource: Resource,
    series: dict[SignalName, MetricSeries],
    results: list[rules.RuleResult],
    snapshot: ObservationSnapshot,
    now: datetime,
    incident_id: str,
) -> Incident:
    triggered = [r for r in results if r.triggered]
    facts, timeline = _build_facts(resource, series, results, snapshot)

    rule_ids = [r.rule_id for r in triggered]
    severity = incident_severity(results)
    timeline.append(
        TimelineEntry(
            at=now,
            kind="incident_opened",
            label=statements.incident_opened_label(rule_ids, severity),
        )
    )

    key_signals: list[KeySignal] = []
    for r in triggered:
        if r.signal is None or any(k.signal == r.signal for k in key_signals):
            continue
        assert r.latest is not None  # a triggered rule implies data
        key_signals.append(KeySignal(signal=r.signal, value=r.latest, unit=series[r.signal].unit))

    # Evidence: every series of the resource, from 60 min before the earliest breach.
    earliest = min(r.breach_start for r in triggered if r.breach_start is not None)
    lookback_start = earliest - thresholds.EVIDENCE_LOOKBACK
    evidence = IncidentEvidence(
        series=[
            s.model_copy(update={"points": [p for p in s.points if p.t >= lookback_start]})
            for s in series.values()
        ]
    )

    return Incident(
        id=incident_id,
        fingerprint=resource.id,
        title=statements.title(_primary(triggered).rule_id, resource.name),
        severity=severity,
        status="open",
        resource_id=resource.id,
        resource_name=resource.name,
        region=resource.region,
        data_origin=resource.data_origin,
        rule_ids=rule_ids,
        first_detected_at=now,
        last_updated_at=now,
        key_signals=key_signals,
        facts=facts,
        timeline=timeline,
        evidence=evidence,
        evidence_hash=_evidence_hash(facts, evidence),
    )


def evaluate(
    snapshot: ObservationSnapshot,
    open_fingerprints: set[str],
    now: datetime,
    allocate_id: Callable[[], str],
) -> EvaluationResult:
    result = EvaluationResult(resources_evaluated=len(snapshot.resources))
    for resource in snapshot.resources:
        series = _series_for(snapshot, resource.id)
        resource_results = rules.evaluate_resource(resource, series)
        result.rule_results.extend(resource_results)
        if not any(r.triggered for r in resource_results) or resource.id in open_fingerprints:
            continue
        result.opened.append(
            _open_incident(resource, series, resource_results, snapshot, now, allocate_id())
        )
    return result
