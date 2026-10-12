"""The severity matrix. The only place severity is decided. The LLM never sets it."""

from sentinel.detection.rules import RuleResult
from sentinel.domain.incidents import SEVERITY_ORDER, Severity

RULE_SEVERITY: dict[str, Severity] = {
    "R-CPU-SAT": "medium",
    "R-CPU-CREDIT": "medium",
    "R-MEM": "medium",
    "R-STATUS": "critical",
    "R-5XX": "high",
    "R-LAT": "medium",
    # Derived: latency and errors together mean users are affected, so at least high.
    "C-USER-IMPACT": "high",
}

# Rules with a lower tier (RuleResult.lower_tier): R-5XX between 2% and 5% is medium.
LOWER_TIER_SEVERITY: dict[str, Severity] = {
    "R-5XX": "medium",
}


def rule_severity(result: RuleResult) -> Severity:
    if result.lower_tier:
        return LOWER_TIER_SEVERITY[result.rule_id]
    return RULE_SEVERITY[result.rule_id]


def incident_severity(results: list[RuleResult]) -> Severity:
    """Highest severity among the triggered rules."""
    triggered = [r for r in results if r.triggered]
    if not triggered:
        raise ValueError("An incident needs at least one triggered rule")
    return max((rule_severity(r) for r in triggered), key=lambda s: SEVERITY_ORDER[s])
