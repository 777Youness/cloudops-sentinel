"""Templates for fact statements and labels. Consistent wording, testable, never LLM-written."""

from datetime import datetime, timedelta

from sentinel.detection import thresholds
from sentinel.detection.rules import Clearance, RuleResult
from sentinel.domain.observations import OpsEvent, SignalName, Unit

SIGNAL_LABELS: dict[SignalName, str] = {
    "cpu_utilization": "CPU utilization",
    "cpu_credit_balance": "CPU credit balance",
    "memory_used": "Memory utilization",
    "status_check_failed": "EC2 status check",
    "latency_p95": "p95 latency",
    "error_rate_5xx": "5xx error rate",
    "request_rate": "Request rate",
}

TITLES: dict[str, str] = {
    "R-CPU-SAT": "Sustained CPU saturation on {name}",
    "R-CPU-CREDIT": "CPU credits exhausted on {name}",
    "R-MEM": "High memory usage on {name}",
    "R-STATUS": "Status check failing on {name}",
    "R-5XX": "Elevated 5xx error rate on {name}",
    "R-LAT": "Latency degradation on {name}",
    "C-USER-IMPACT": "User-facing errors and latency on {name}",
}


def hhmm(t: datetime) -> str:
    return t.strftime("%H:%M UTC")


def minutes(d: timedelta) -> int:
    return int(d.total_seconds() // 60)


def value(v: float, unit: Unit) -> str:
    """A measured value with its unit."""
    match unit:
        case "percent":
            return f"{v:.1f}%"
        case "ms":
            return f"{v:.0f} ms"
        case "credits":
            return f"{v:.1f} credits"
        case "per_minute":
            return f"{v:.0f}/min"
        case "count":
            return f"{v:g}"


def limit(v: float, unit: Unit) -> str:
    """A threshold with its unit, without trailing zeros (90%, 5 credits, 540 ms)."""
    match unit:
        case "percent":
            return f"{v:g}%"
        case "ms":
            return f"{v:.0f} ms"
        case "credits":
            return f"{v:g} credits"
        case "per_minute":
            return f"{v:g}/min"
        case "count":
            return f"{v:g}"


def title(rule_id: str, resource_name: str) -> str:
    return TITLES[rule_id].format(name=resource_name)


def breach_fact(r: RuleResult, unit: Unit) -> str:
    assert r.signal and r.duration and r.breach_start and r.peak is not None
    assert r.threshold is not None
    since = f"for {minutes(r.duration)} min since {hhmm(r.breach_start)}"
    match r.rule_id:
        case "R-CPU-CREDIT":
            return (
                f"CPU credit balance at or below {limit(r.threshold, unit)} {since} "
                f"(lowest {value(r.peak, unit)})"
            )
        case "R-STATUS":
            return f"EC2 status check failing {since}"
        case "R-LAT":
            assert r.baseline is not None
            return (
                f"p95 latency at or above {limit(r.threshold, unit)} {since} "
                f"(peak {value(r.peak, unit)}, baseline {value(r.baseline, unit)})"
            )
        case _:
            return (
                f"{SIGNAL_LABELS[r.signal]} at or above {limit(r.threshold, unit)} {since} "
                f"(peak {value(r.peak, unit)})"
            )


def within_normal_fact(r: RuleResult, unit: Unit) -> str:
    assert r.signal and r.latest is not None and r.threshold is not None
    latest = f"latest {value(r.latest, unit)}"
    match r.rule_id:
        case "R-CPU-CREDIT":
            return f"CPU credit balance above {limit(r.threshold, unit)} ({latest})"
        case "R-STATUS":
            return "EC2 status check passing at the latest datapoint"
        case _:
            return f"{SIGNAL_LABELS[r.signal]} below {limit(r.threshold, unit)} ({latest})"


def data_gap_fact(r: RuleResult) -> str:
    assert r.signal
    if r.reason == "insufficient_traffic":
        return (
            f"Fewer than {thresholds.MIN_REQUESTS} requests while "
            f"{SIGNAL_LABELS[r.signal].lower()} was elevated: too little traffic "
            f"to evaluate {r.rule_id}"
        )
    return f"Not enough {SIGNAL_LABELS[r.signal].lower()} data to evaluate {r.rule_id}"


def breach_start_label(r: RuleResult, unit: Unit) -> str:
    assert r.signal and r.threshold is not None
    match r.rule_id:
        case "R-CPU-CREDIT":
            return f"CPU credit balance fell to {limit(r.threshold, unit)}"
        case "R-STATUS":
            return "EC2 status check started failing"
        case _:
            return f"{SIGNAL_LABELS[r.signal]} reached {limit(r.threshold, unit)}"


def incident_opened_label(rule_ids: list[str], severity: str) -> str:
    return f"Incident opened by {', '.join(rule_ids)}, severity {severity}"


EVENT_KIND_LABELS = {"deployment": "Deployment"}


def event_fact(event: OpsEvent) -> str:
    return f"{EVENT_KIND_LABELS[event.kind]} at {hhmm(event.at)}: {event.label}"


def event_label(event: OpsEvent) -> str:
    return f"{EVENT_KIND_LABELS[event.kind]}: {event.label}"


def cleared_fact(c: Clearance, unit: Unit) -> str:
    assert c.clean_since is not None
    since = f"for {minutes(c.duration)} min since {hhmm(c.clean_since)}"
    match c.rule_id:
        case "R-CPU-CREDIT":
            return f"CPU credit balance above {limit(c.threshold, unit)} {since}"
        case "R-STATUS":
            return f"EC2 status check passing {since}"
        case _:
            return f"{SIGNAL_LABELS[c.signal]} below {limit(c.threshold, unit)} {since}"


def incident_updated_label(added_rules: list[str], old: str, new: str, events: int) -> str:
    parts = []
    if added_rules:
        parts.append(f"{', '.join(added_rules)} added")
    if new != old:
        parts.append(f"severity raised from {old} to {new}")
    if events:
        parts.append(f"{events} new event{'s' if events > 1 else ''}")
    return "Incident updated: " + "; ".join(parts)


def incident_resolved_label() -> str:
    minutes_clean = minutes(thresholds.RESOLVE_CLEAN_DURATION)
    return f"Incident resolved: every condition clear for at least {minutes_clean} min"
