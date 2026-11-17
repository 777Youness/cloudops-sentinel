"""Manual, opt-in evaluation of the configured LLM provider on reliability cases A-E.

Not a test: automated tests never call a real LLM (CLAUDE.md section 10). This script runs
the five cases of tests/investigation_cases.py through the real InvestigationService
(same bundle, prompt, validator and single retry as the console), with an in-memory store:
your SQLite databases are never opened.

Bounded: at most 5 cases x 2 attempts = 10 provider calls, each capped by
SENTINEL_LLM_MAX_TOKENS and SENTINEL_LLM_TIMEOUT_SECONDS. Nothing is sent without --yes.
The API key is read by Settings like the app does and is never printed or saved.

Run from backend/ (configuration from the environment or backend/.env, as for the app):
    uv run python -m evals.investigation_reliability            # dry run: what would be sent
    uv run python -m evals.investigation_reliability --yes      # call the provider
    uv run python -m evals.investigation_reliability --yes --cases A,D --save

What it measures: whether the model's replies pass validation, how often the first reply
is rejected, and the confidence levels. Whether the text reasons well is for YOU to judge:
each case prints what a good answer looks like.
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from sentinel.clock import SystemClock
from sentinel.config import Settings
from sentinel.investigation.prompt import PROMPT_VERSION
from sentinel.main import build_provider
from sentinel.services.investigation import InvestigationService
from sentinel.store.sqlite import SqliteStore
from tests.investigation_cases import CASES

EXPECTED = {
    "A": "Two co-occurring breaches kept distinct; no established cause; CPU near 1% read as "
    "evidence against throttling; alternatives; checks that would confirm or refute.",
    "B": "No CPU explanation (CPU, credits, memory are normal); application, deployment or "
    "dependency kept open; deployment data noted as not collected.",
    "C": "No customer-facing outage or error claim; low balance not equated with throttling.",
    "D": "A confident EC2-level diagnosis is allowed: the failing status check is direct.",
    "E": "Gaps named as unknown; no claim that logs or deployments were inspected.",
}
EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"


def _host(url: str | None) -> str:
    try:
        return httpx.URL(url or "").host or "?"
    except (httpx.InvalidURL, ValueError, TypeError):
        return "?"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cases", default=",".join(CASES), help="for example A,D")
    parser.add_argument("--yes", action="store_true", help="really call the provider")
    parser.add_argument("--save", action="store_true", help="save results in docs/examples/")
    args = parser.parse_args()
    names = [c.strip().upper() for c in args.cases.split(",") if c.strip()]
    unknown = [n for n in names if n not in CASES]
    if unknown:
        parser.error(f"unknown case(s): {', '.join(unknown)}")

    settings = Settings()
    provider, status = build_provider(settings)
    if provider is None:
        print("The provider is selected but incomplete: set SENTINEL_LLM_BASE_URL and MODEL.")
        return 2
    remote = provider.name != "mock"
    where = _host(settings.llm_base_url) if remote else "none (mock, no network)"
    print(f"provider {provider.name}, model {provider.model}, host {where}")
    print(f"prompt {PROMPT_VERSION}, cases {', '.join(names)}, at most {2 * len(names)} calls")
    if remote and not args.yes:
        print("Dry run: nothing was sent. Add --yes to call the provider.")
        return 0

    clock = SystemClock()
    results = []
    for name in names:
        incident = CASES[name]()
        store = SqliteStore(":memory:")
        store.add_incident(incident)
        run = InvestigationService(store, provider, status, clock).run(incident.id)
        inv = run.investigation
        findings = inv.findings.model_dump() if inv.findings else None
        results.append(
            {
                "case": name,
                "expected": EXPECTED[name],
                "facts": [f"{f.id} {f.kind}: {f.statement}" for f in incident.facts],
                "status": inv.status,
                "attempts": inv.attempts,
                "error": inv.error.model_dump() if inv.error else None,
                "findings": findings,
            }
        )
        print(f"\n=== Case {name}: {inv.status}, {inv.attempts} attempt(s) ===")
        print(f"expected: {EXPECTED[name]}")
        if inv.error:
            print(f"error: {inv.error.code}: {inv.error.message}")
        if findings:
            print(f"summary: {findings['summary']}")
            for h in findings["hypotheses"]:
                print(f"  {h['id']} [{h['confidence']}] {h['statement']} {h['cites']}")
            for c in findings["next_checks"]:
                print(f"  {c['id']} check: {c['description']}")
            for r in findings["remediation"]:
                print(f"  {r['id']} remediation: {r['description']}")
            for limit in findings["limitations"]:
                print(f"  limitation: {limit}")

    completed = [r for r in results if r["status"] == "completed"]
    retried = [r for r in results if r["attempts"] == 2]
    print(f"\n{len(completed)}/{len(results)} completed; first reply rejected in {len(retried)}.")

    if args.save:
        model = re.sub(r"[^A-Za-z0-9.-]+", "-", provider.model).strip("-")
        path = EXAMPLES / f"{datetime.now(UTC):%Y-%m-%d}-{model}-reliability-eval.json"
        record = {
            "provider": provider.name,
            "model": provider.model,
            "prompt_version": PROMPT_VERSION,
            "run_at": datetime.now(UTC).isoformat(),
            "results": results,
        }
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", "utf-8")
        print(f"saved {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
