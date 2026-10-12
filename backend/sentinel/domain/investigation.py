"""Investigations: an LLM's interpretation of an incident's stored facts.

Two kinds of model live here:
  - `InvestigationFindings` and its parts: the strict shape the LLM must return. Unknown
    fields are rejected (`extra="forbid"`), so the model cannot add a severity, a risk
    level or a command. Text lengths and citations are checked by investigation/validator.py.
  - `Investigation`: one saved run, stored separately from the incident. An investigation
    never changes the incident's facts, severity or evidence.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

Confidence = Literal["low", "medium", "high"]
RunStatus = Literal["completed", "failed"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hypothesis(_Strict):
    id: str  # "H1"
    statement: str
    confidence: Confidence
    cites: list[str]  # fact ids, at least one (validator)


class NextCheck(_Strict):
    id: str  # "C1"
    description: str
    cites: list[str]


class RemediationOption(_Strict):
    """Advice for a human. Descriptive text only: there is no command or action field."""

    id: str  # "R1"
    description: str
    requires_human: Literal[True]
    cites: list[str]


class InvestigationFindings(_Strict):
    summary: str
    hypotheses: list[Hypothesis]
    next_checks: list[NextCheck] = []
    remediation: list[RemediationOption] = []
    limitations: list[str] = []


class InvestigationError(BaseModel):
    """Why a run failed: a provider error (timeout, auth, ...) or a validation reason."""

    code: str
    message: str
    hint: str | None = None


class Investigation(BaseModel):
    id: str  # "INV-0001"
    incident_id: str
    status: RunStatus
    provider: str
    model: str
    prompt_version: str
    started_at: AwareDatetime
    finished_at: AwareDatetime
    attempts: int  # provider calls made: 1, or 2 after one retry for invalid output
    # The incident's evidence hash when the bundle was built. If the incident's hash has
    # changed since (new facts merged, resolution), the investigation is outdated.
    evidence_hash: str
    fact_ids: list[str]  # the facts the model was given
    findings: InvestigationFindings | None = None
    error: InvestigationError | None = None


class InvestigationResult(BaseModel):
    """What the API returns: the latest run plus what can only be known at read time."""

    investigation: Investigation
    outdated: bool
    incident_evidence_hash: str
    runs: int  # every run is kept; this is how many exist for the incident
