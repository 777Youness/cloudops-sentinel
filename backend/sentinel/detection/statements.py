"""Templates for fact statements and labels. Consistent wording, testable, never LLM-written."""

from datetime import datetime, timedelta


def hhmm(t: datetime) -> str:
    return t.strftime("%H:%M UTC")


def minutes(d: timedelta) -> int:
    return int(d.total_seconds() // 60)


def cpu_saturation_fact(threshold: float, duration: timedelta, peak: float, start: datetime) -> str:
    return (
        f"CPU utilization at or above {threshold:g}% for {minutes(duration)} min "
        f"since {hhmm(start)} (peak {peak:.1f}%)"
    )


def cpu_saturation_title(resource_name: str) -> str:
    return f"Sustained CPU saturation on {resource_name}"


def breach_start_label(threshold: float) -> str:
    return f"CPU reached {threshold:g}%"


def incident_opened_label(rule_ids: list[str], severity: str) -> str:
    return f"Incident opened by {', '.join(rule_ids)}, severity {severity}"
