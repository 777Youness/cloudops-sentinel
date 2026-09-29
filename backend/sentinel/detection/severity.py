"""The severity matrix. The only place severity is decided. The LLM never sets it."""

from sentinel.domain.incidents import SEVERITY_ORDER, Severity

RULE_SEVERITY: dict[str, Severity] = {
    "R-CPU-SAT": "medium",
}


def incident_severity(rule_ids: list[str]) -> Severity:
    """Highest severity among the triggered rules."""
    if not rule_ids:
        raise ValueError("An incident needs at least one triggered rule")
    return max((RULE_SEVERITY[r] for r in rule_ids), key=lambda s: SEVERITY_ORDER[s])
