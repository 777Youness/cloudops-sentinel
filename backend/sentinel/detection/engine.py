"""The detection engine: observations + open incidents -> opened, updated, resolved incidents.

Pure: no I/O, no clock (time is passed in), no knowledge of AWS or HTTP. It never mutates
the incidents it is given; it returns new versions for the caller to store.

Lifecycle (one open incident per resource, fingerprint = resource id):
  - rules trigger and the resource has no open incident -> open one with every triggered rule;
  - rules trigger and an incident is open -> merge: new rules and new events are appended
    as new facts (existing facts never change: investigations cite them by id) and severity
    can only rise while open. Re-observing the same situation changes nothing;
  - nothing triggers and an incident is open -> resolve it once every one of its
    conditions has been clean (data present, not breaching) for RESOLVE_CLEAN_DURATION;
  - after resolution, a new breach opens a new incident.
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
from sentinel.domain.observations import (
    MetricPoint,
    MetricSeries,
    ObservationSnapshot,
    OpsEvent,
    Resource,
    SignalName,
)

# Rules that could not be evaluated become data_gap facts: "we could not check this".
GAP_REASONS = ("insufficient_data", "insufficient_traffic")
BREACH_KINDS = ("threshold_breach", "baseline_deviation")


@dataclass
class EvaluationResult:
    opened: list[Incident] = field(default_factory=list)
    updated: list[Incident] = field(default_factory=list)
    resolved: list[Incident] = field(default_factory=list)
    rule_results: list[rules.RuleResult] = field(default_factory=list)
    resources_evaluated: int = 0
    rules_evaluated: int = len(rules.RULE_IDS)


def _series_for(snapshot: ObservationSnapshot, resource_id: str) -> dict[SignalName, MetricSeries]:
    return {s.signal: s for s in snapshot.series if s.resource_id == resource_id}


def _events_for(snapshot: ObservationSnapshot, resource_id: str, since: datetime) -> list[OpsEvent]:
    events = [e for e in snapshot.events if e.resource_id == resource_id and e.at >= since]
    return sorted(events, key=lambda e: e.at)


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


def _sorted_rule_ids(rule_ids: set[str]) -> list[str]:
    return [r for r in rules.RULE_IDS if r in rule_ids]


class _FactBuilder:
    """Appends facts with sequential ids (F1, F2, ...) continuing after existing ones."""

    def __init__(self, resource: Resource, existing: int = 0) -> None:
        self.resource = resource
        self.facts: list[Fact] = []
        self.timeline: list[TimelineEntry] = []
        self._offset = existing

    def _next_id(self) -> str:
        return f"F{self._offset + len(self.facts) + 1}"

    def breach(self, r: rules.RuleResult, s: MetricSeries) -> None:
        assert r.breach_start and r.breach_end and r.signal
        fact = Fact(
            id=self._next_id(),
            kind="baseline_deviation" if r.baseline is not None else "threshold_breach",
            statement=statements.breach_fact(r, s.unit),
            source=s.source,
            resource_id=self.resource.id,
            observed_at=r.breach_end,
            window=TimeWindow(start=r.breach_start, end=r.breach_end),
            rule_id=r.rule_id,
            signal=r.signal,
            value=r.peak,
            baseline=r.baseline,
            threshold=r.threshold,
            unit=s.unit,
        )
        self.facts.append(fact)
        self.timeline.append(
            TimelineEntry(
                at=r.breach_start,
                kind="breach_start",
                label=statements.breach_start_label(r, s.unit),
                fact_id=fact.id,
            )
        )

    def event(self, e: OpsEvent) -> None:
        fact = Fact(
            id=self._next_id(),
            kind="event",
            statement=statements.event_fact(e),
            source=e.source,
            resource_id=self.resource.id,
            observed_at=e.at,
            event_id=e.id,
        )
        self.facts.append(fact)
        self.timeline.append(
            TimelineEntry(at=e.at, kind="event", label=statements.event_label(e), fact_id=fact.id)
        )

    def within_normal(self, r: rules.RuleResult, s: MetricSeries) -> None:
        self.facts.append(
            Fact(
                id=self._next_id(),
                kind="within_normal",
                statement=statements.within_normal_fact(r, s.unit),
                source=s.source,
                resource_id=self.resource.id,
                observed_at=s.points[-1].t,
                rule_id=r.rule_id,
                signal=r.signal,
                value=r.latest,
                threshold=r.threshold,
                unit=s.unit,
            )
        )

    def cleared(self, c: rules.Clearance, s: MetricSeries) -> None:
        assert c.clean_since is not None
        self.facts.append(
            Fact(
                id=self._next_id(),
                kind="within_normal",
                statement=statements.cleared_fact(c, s.unit),
                source=s.source,
                resource_id=self.resource.id,
                observed_at=s.points[-1].t,
                window=TimeWindow(start=c.clean_since, end=s.points[-1].t),
                rule_id=c.rule_id,
                signal=c.signal,
                value=c.latest,
                threshold=c.threshold,
                unit=s.unit,
            )
        )

    def data_gap(self, r: rules.RuleResult, snapshot: ObservationSnapshot) -> None:
        self.facts.append(
            Fact(
                id=self._next_id(),
                kind="data_gap",
                statement=statements.data_gap_fact(r),
                source="detection",
                resource_id=self.resource.id,
                observed_at=snapshot.window_end,
                window=TimeWindow(start=snapshot.window_start, end=snapshot.window_end),
                rule_id=r.rule_id,
                signal=r.signal,
            )
        )


def _key_signals(
    triggered: list[rules.RuleResult], series: dict[SignalName, MetricSeries]
) -> list[KeySignal]:
    key_signals: list[KeySignal] = []
    for r in triggered:
        if r.signal is None or any(k.signal == r.signal for k in key_signals):
            continue
        assert r.latest is not None  # a triggered rule implies data
        key_signals.append(KeySignal(signal=r.signal, value=r.latest, unit=series[r.signal].unit))
    return key_signals


def _merge_series(old: list[MetricSeries], new: list[MetricSeries]) -> list[MetricSeries]:
    """Union of evidence points per signal; for the same timestamp the newer value wins."""
    merged: dict[SignalName, MetricSeries] = {s.signal: s for s in old}
    for s in new:
        if s.signal not in merged:
            merged[s.signal] = s
            continue
        points: dict[datetime, MetricPoint] = {p.t: p for p in merged[s.signal].points}
        points.update({p.t: p for p in s.points})
        merged[s.signal] = s.model_copy(update={"points": [points[t] for t in sorted(points)]})
    return list(merged.values())


def _evidence_series(series: dict[SignalName, MetricSeries], since: datetime) -> list[MetricSeries]:
    return [
        s.model_copy(update={"points": [p for p in s.points if p.t >= since]})
        for s in series.values()
    ]


def _open_incident(
    resource: Resource,
    series: dict[SignalName, MetricSeries],
    results: list[rules.RuleResult],
    snapshot: ObservationSnapshot,
    now: datetime,
    incident_id: str,
) -> Incident:
    """Facts in a fixed order: breaches, events, what was checked and normal, data gaps."""
    triggered = [r for r in results if r.triggered]
    earliest = min(r.breach_start for r in triggered if r.breach_start is not None)
    lookback_start = earliest - thresholds.EVIDENCE_LOOKBACK

    b = _FactBuilder(resource)
    for r in triggered:
        if r.signal is not None:  # C-USER-IMPACT has no observation of its own
            b.breach(r, series[r.signal])
    for e in _events_for(snapshot, resource.id, lookback_start):
        b.event(e)
    for r in results:
        if r.reason == "below_threshold" and r.signal is not None:
            b.within_normal(r, series[r.signal])
    for r in results:
        if r.reason in GAP_REASONS:
            b.data_gap(r, snapshot)

    rule_ids = [r.rule_id for r in triggered]
    severity = incident_severity(results)
    timeline = sorted(b.timeline, key=lambda e: e.at)
    timeline.append(
        TimelineEntry(
            at=now,
            kind="incident_opened",
            label=statements.incident_opened_label(rule_ids, severity),
        )
    )
    evidence = IncidentEvidence(series=_evidence_series(series, lookback_start))
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
        key_signals=_key_signals(triggered, series),
        facts=b.facts,
        timeline=timeline,
        evidence=evidence,
        evidence_hash=_evidence_hash(b.facts, evidence),
    )


def _merge(
    incident: Incident,
    resource: Resource,
    series: dict[SignalName, MetricSeries],
    results: list[rules.RuleResult],
    snapshot: ObservationSnapshot,
    now: datetime,
) -> Incident | None:
    """Return the updated incident, or None if nothing meaningful changed."""
    triggered = [r for r in results if r.triggered]
    new_rules = [r for r in triggered if r.rule_id not in incident.rule_ids]
    recorded_events = {f.event_id for f in incident.facts if f.event_id}
    first_breach = min(
        f.window.start for f in incident.facts if f.kind in BREACH_KINDS and f.window
    )
    since = first_breach - thresholds.EVIDENCE_LOOKBACK
    new_events = [
        e for e in _events_for(snapshot, resource.id, since) if e.id not in recorded_events
    ]
    current = incident_severity(results)
    severity = max(incident.severity, current, key=lambda s: SEVERITY_ORDER[s])
    if not new_rules and not new_events and severity == incident.severity:
        return None

    b = _FactBuilder(resource, existing=len(incident.facts))
    for r in new_rules:
        if r.signal is not None:
            b.breach(r, series[r.signal])
    for e in new_events:
        b.event(e)

    facts = incident.facts + b.facts
    rule_ids = _sorted_rule_ids(set(incident.rule_ids) | {r.rule_id for r in new_rules})
    # Chronological: a newly merged breach may have started before the incident opened.
    timeline = sorted(incident.timeline + b.timeline, key=lambda e: e.at)
    timeline.append(
        TimelineEntry(
            at=now,
            kind="incident_updated",
            label=statements.incident_updated_label(
                [r.rule_id for r in new_rules], incident.severity, severity, len(new_events)
            ),
        )
    )
    evidence = IncidentEvidence(
        series=_merge_series(incident.evidence.series, _evidence_series(series, since))
    )
    title = incident.title
    if severity != incident.severity:  # the situation got worse: name it after what is now worst
        title = statements.title(_primary(triggered).rule_id, resource.name)
    return incident.model_copy(
        update={
            "title": title,
            "severity": severity,
            "rule_ids": rule_ids,
            "last_updated_at": now,
            "key_signals": _key_signals(triggered, series),
            "facts": facts,
            "timeline": timeline,
            "evidence": evidence,
            "evidence_hash": _evidence_hash(facts, evidence),
        }
    )


def _try_resolve(
    incident: Incident,
    resource: Resource,
    series: dict[SignalName, MetricSeries],
    now: datetime,
) -> Incident | None:
    """Resolve if every signal-based rule of the incident has been clear long enough."""
    clearances: list[rules.Clearance] = []
    for rule_id in incident.rule_ids:
        if rule_id not in rules.RULE_CONDITIONS:
            continue  # derived rules (C-USER-IMPACT) clear when their parts do
        signal, threshold, _ = rules.RULE_CONDITIONS[rule_id]
        if threshold is None:  # R-LAT: the threshold recorded when it triggered
            threshold = next(
                f.threshold
                for f in reversed(incident.facts)
                if f.rule_id == rule_id and f.threshold is not None
            )
        c = rules.clearance(series.get(signal), rule_id, threshold)
        if not c.cleared:
            return None
        clearances.append(c)

    b = _FactBuilder(resource, existing=len(incident.facts))
    for c in clearances:
        b.cleared(c, series[c.signal])
    facts = incident.facts + b.facts
    timeline = incident.timeline + [
        TimelineEntry(at=now, kind="incident_resolved", label=statements.incident_resolved_label())
    ]
    # Keep the clean window as evidence too: the charts must show the recovery the
    # resolution facts describe, not end on the last breaching datapoint.
    first_breach = min(
        f.window.start for f in incident.facts if f.kind in BREACH_KINDS and f.window
    )
    since = first_breach - thresholds.EVIDENCE_LOOKBACK
    evidence = IncidentEvidence(
        series=_merge_series(incident.evidence.series, _evidence_series(series, since))
    )
    return incident.model_copy(
        update={
            "status": "resolved",
            "resolved_at": now,
            "last_updated_at": now,
            "facts": facts,
            "timeline": timeline,
            "evidence": evidence,
            "evidence_hash": _evidence_hash(facts, evidence),
        }
    )


def evaluate(
    snapshot: ObservationSnapshot,
    open_incidents: list[Incident],
    now: datetime,
    allocate_id: Callable[[], str],
) -> EvaluationResult:
    by_fingerprint = {i.fingerprint: i for i in open_incidents}
    result = EvaluationResult(resources_evaluated=len(snapshot.resources))
    for resource in snapshot.resources:
        series = _series_for(snapshot, resource.id)
        resource_results = rules.evaluate_resource(resource, series)
        result.rule_results.extend(resource_results)
        existing = by_fingerprint.get(resource.id)

        if any(r.triggered for r in resource_results):
            if existing is None:
                result.opened.append(
                    _open_incident(resource, series, resource_results, snapshot, now, allocate_id())
                )
            elif updated := _merge(existing, resource, series, resource_results, snapshot, now):
                result.updated.append(updated)
        elif existing is not None and (resolved := _try_resolve(existing, resource, series, now)):
            result.resolved.append(resolved)
    return result
