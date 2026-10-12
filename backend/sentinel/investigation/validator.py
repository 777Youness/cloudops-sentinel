"""Validates an LLM reply before anything is saved. Pure: text and fact ids in, findings out.

Invalid output is rejected with a reason, never silently repaired. The service gives the
model one retry with that reason; a second rejection makes the run "failed".

Rejection reasons (one test each in tests/unit/test_investigation_validator.py):
  not_json              the reply is not one JSON object
  forbidden_field       severity, risk, a command or another field the model may not set
  remediation_not_human a remediation option without requires_human = true
  schema_invalid        anything else that does not match InvestigationFindings
  no_hypotheses         no hypothesis at all
  missing_citation      a hypothesis, check or remediation option cites nothing
  unknown_fact          a citation to a fact id that is not in the evidence
  duplicate_id          two items share an id
  text_too_long         a text above MAX_TEXT characters
  command_in_text       a remediation or check that contains a shell command
"""

import json
import re
from typing import Any

from sentinel.domain.investigation import InvestigationFindings

MAX_TEXT = 300
MAX_ITEMS = 5

# Keys the model may never set, at any depth. The strict schema would reject them too;
# checking first gives a precise reason, which makes the single retry more useful.
FORBIDDEN_KEYS = {
    "severity",
    "risk",
    "risk_level",
    "priority",
    "command",
    "commands",
    "action",
    "actions",
    "execute",
    "script",
}

# Defence in depth for "descriptive text only". The primary defence is that the console
# shows text and never executes anything. Patterns: backticks, shell prompts, sudo/rm/
# systemctl/kubectl invocations, and AWS CLI calls ("aws ec2 reboot-instances").
COMMAND_PATTERNS = [
    re.compile(r"`"),
    re.compile(r"(^|\n)\s*\$\s"),
    re.compile(r"\b(sudo|systemctl|kubectl)\s+\S"),
    re.compile(r"\brm\s+-\w"),
    re.compile(r"\baws\s+[a-z0-9-]+\s+[a-z]+-[a-z-]+"),
]


class ValidationFailure(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        # The detail can quote the model's own text. It is saved, returned by the API and
        # sent back on the retry, so it is bounded like every other text.
        detail = detail if len(detail) <= MAX_TEXT else detail[: MAX_TEXT - 1] + "…"
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def _quote_ids(ids: list[str]) -> str:
    """Model-supplied ids, shortened, for an error message."""
    shown = [i if len(i) <= 20 else i[:19] + "…" for i in ids[:5]]
    return ", ".join(shown) + (f" and {len(ids) - 5} more" if len(ids) > 5 else "")


def _parse_json(text: str) -> Any:
    candidate = text.strip()
    # A single fenced block (```json ... ```) is formatting, not content: unwrap it.
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValidationFailure("not_json", f"The reply is not valid JSON ({exc.msg}).") from exc


def _forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                found.add(str(key))
            found |= _forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            found |= _forbidden_keys(child)
    return found


def _texts(findings: InvestigationFindings) -> list[tuple[str, str]]:
    texts = [("summary", findings.summary)]
    texts += [(h.id, h.statement) for h in findings.hypotheses]
    texts += [(c.id, c.description) for c in findings.next_checks]
    texts += [(r.id, r.description) for r in findings.remediation]
    texts += [(f"limitation {i + 1}", t) for i, t in enumerate(findings.limitations)]
    return texts


def validate_output(text: str, fact_ids: set[str]) -> InvestigationFindings:
    data = _parse_json(text)
    if not isinstance(data, dict):
        raise ValidationFailure("not_json", "The reply must be one JSON object.")

    forbidden = _forbidden_keys(data)
    if forbidden:
        raise ValidationFailure(
            "forbidden_field", f"Fields that may not be set: {_quote_ids(sorted(forbidden))}."
        )
    for option in data.get("remediation") or []:
        if isinstance(option, dict) and option.get("requires_human") is not True:
            raise ValidationFailure(
                "remediation_not_human",
                f"Remediation {option.get('id', '?')} must have requires_human: true.",
            )

    try:
        findings = InvestigationFindings.model_validate(data)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        errors = getattr(exc, "errors", lambda: [])()
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", [])) or "reply"
        raise ValidationFailure(
            "schema_invalid", f"{where}: {first.get('msg', 'does not match the schema')}."
        ) from exc

    if not findings.hypotheses:
        raise ValidationFailure("no_hypotheses", "At least one hypothesis is required.")

    for where, text_value in _texts(findings):
        if not text_value.strip():
            raise ValidationFailure("schema_invalid", f"{where} is empty.")
    for item in [*findings.hypotheses, *findings.next_checks, *findings.remediation]:
        if not item.id.strip():
            raise ValidationFailure("schema_invalid", "Every item needs a non-empty id.")

    lists = (findings.hypotheses, findings.next_checks, findings.remediation)
    if any(len(items) > MAX_ITEMS for items in lists) or len(findings.limitations) > MAX_ITEMS:
        raise ValidationFailure("schema_invalid", f"At most {MAX_ITEMS} items per list.")

    items = [*findings.hypotheses, *findings.next_checks, *findings.remediation]
    for item in items:
        if not item.cites:
            raise ValidationFailure("missing_citation", f"{item.id} cites no fact.")
    for item in items:
        unknown = sorted(set(item.cites) - fact_ids)
        if unknown:
            raise ValidationFailure(
                "unknown_fact",
                f"{_quote_ids([item.id])} cites {_quote_ids(unknown)}, which "
                f"{'is' if len(unknown) == 1 else 'are'} not in the evidence.",
            )

    ids = [item.id for item in items]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValidationFailure("duplicate_id", f"Duplicate ids: {_quote_ids(duplicates)}.")

    for where, text_value in _texts(findings):
        if len(text_value) > MAX_TEXT:
            raise ValidationFailure(
                "text_too_long", f"{where} is {len(text_value)} characters (max {MAX_TEXT})."
            )

    for item in [*findings.next_checks, *findings.remediation]:
        if any(p.search(item.description) for p in COMMAND_PATTERNS):
            raise ValidationFailure(
                "command_in_text",
                f"{item.id} contains a command. Describe the step in plain words.",
            )

    return findings
