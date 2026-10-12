"""Investigations: the only code path that calls an LLM provider (POST only).

    stored incident -> evidence bundle -> prompt -> provider -> validator
                    -> (one retry with the rejection reason) -> saved Investigation

The incident is read, never written: facts, severity, timeline and evidence are untouched.
Every run is saved, including failed ones, in its own table.
"""

import logging
import threading

from sentinel.clock import Clock
from sentinel.domain.errors import (
    InvestigationInProgressError,
    LlmNotConfiguredError,
    NotFoundError,
)
from sentinel.domain.incidents import Incident, InvestigationStatus
from sentinel.domain.investigation import (
    Investigation,
    InvestigationError,
    InvestigationFindings,
    InvestigationResult,
)
from sentinel.domain.system import LlmStatus
from sentinel.investigation.bundle import build_bundle, fact_ids
from sentinel.investigation.prompt import PROMPT_VERSION, build_prompt
from sentinel.investigation.providers.base import LlmProvider, ProviderError
from sentinel.investigation.validator import ValidationFailure, validate_output
from sentinel.store.base import Store

log = logging.getLogger("sentinel.investigation")

# One call, plus one retry if the reply is rejected by the validator (CLAUDE.md).
MAX_ATTEMPTS = 2


def is_outdated(investigation: Investigation, incident: Incident) -> bool:
    return investigation.evidence_hash != incident.evidence_hash


def summary_status(investigation: Investigation | None, incident: Incident) -> InvestigationStatus:
    if investigation is None:
        return "not_run"
    if investigation.status == "failed":
        return "failed"
    return "outdated" if is_outdated(investigation, incident) else "completed"


class InvestigationService:
    def __init__(
        self, store: Store, provider: LlmProvider | None, llm_status: LlmStatus, clock: Clock
    ) -> None:
        self._store = store
        self._provider = provider
        self.llm_status = llm_status
        self._clock = clock
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _incident(self, incident_id: str) -> Incident:
        incident = self._store.get_incident(incident_id)
        if incident is None:
            raise NotFoundError(
                f"Incident {incident_id} not found.",
                hint="There is no incident with this ID in the local history.",
            )
        return incident

    def _lock_for(self, incident_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(incident_id, threading.Lock())

    def latest(self, incident_id: str) -> InvestigationResult:
        """Read only: never calls the provider."""
        incident = self._incident(incident_id)
        investigation = self._store.latest_investigation(incident_id)
        if investigation is None:
            raise NotFoundError(
                f"No investigation has been run for {incident_id}.",
                hint="Run one with POST /api/v1/incidents/{id}/investigation.",
            )
        return InvestigationResult(
            investigation=investigation,
            outdated=is_outdated(investigation, incident),
            incident_evidence_hash=incident.evidence_hash,
            runs=self._store.count_investigations(incident_id),
        )

    def run(self, incident_id: str) -> InvestigationResult:
        incident = self._incident(incident_id)
        if self._provider is None:
            raise LlmNotConfiguredError(
                "The investigation provider is not configured.",
                hint="Set SENTINEL_LLM_BASE_URL and SENTINEL_LLM_MODEL, or use "
                "SENTINEL_LLM_PROVIDER=mock.",
            )
        lock = self._lock_for(incident_id)
        if not lock.acquire(blocking=False):
            raise InvestigationInProgressError(
                f"An investigation of {incident_id} is already running.",
                hint="Wait for it to finish, then reload.",
            )
        try:
            investigation = self._investigate(incident, self._provider)
            with self._store.transaction():
                investigation = investigation.model_copy(
                    update={"id": self._store.next_investigation_id()}
                )
                self._store.add_investigation(investigation)
                runs = self._store.count_investigations(incident_id)
                # A sync may have merged new facts while the provider was answering.
                current = self._incident(incident_id)
        finally:
            lock.release()
        log.info(
            "investigation %s of %s: %s after %d attempt(s)",
            investigation.id,
            incident_id,
            investigation.status,
            investigation.attempts,
        )
        return InvestigationResult(
            investigation=investigation,
            outdated=is_outdated(investigation, current),
            incident_evidence_hash=current.evidence_hash,
            runs=runs,
        )

    def _investigate(self, incident: Incident, provider: LlmProvider) -> Investigation:
        bundle = build_bundle(incident)
        allowed = fact_ids(bundle)
        started = self._clock.now()
        findings: InvestigationFindings | None = None
        error: InvestigationError | None = None
        previous: str | None = None
        attempts = 0

        while attempts < MAX_ATTEMPTS:
            attempts += 1
            try:
                reply = provider.complete(build_prompt(bundle, previous))
            except ProviderError as exc:
                # No reply at all: retrying the same request rarely helps. Report it.
                error = InvestigationError(code=exc.code, message=exc.message, hint=exc.hint)
                break
            try:
                findings = validate_output(reply, allowed)
                error = None
                break
            except ValidationFailure as exc:
                previous = f"{exc.reason}: {exc.detail}"
                error = InvestigationError(
                    code=exc.reason,
                    message=exc.detail,
                    hint="The model's reply was rejected after one retry. Run it again, or "
                    "use a model that follows JSON instructions more reliably.",
                )

        return Investigation(
            id="pending",
            incident_id=incident.id,
            status="completed" if findings else "failed",
            provider=provider.name,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            started_at=started,
            finished_at=self._clock.now(),
            attempts=attempts,
            evidence_hash=incident.evidence_hash,
            fact_ids=sorted(allowed, key=lambda f: int(f[1:])),
            findings=findings,
            error=error,
        )
