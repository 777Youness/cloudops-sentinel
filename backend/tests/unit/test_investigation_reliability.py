"""Investigation reliability: cases A-E (tests/investigation_cases.py), no network.

What these tests can prove: what the model is TOLD (bundle, prompt), what is REJECTED
(validator), and that the mock never makes the unsupported claims. What they cannot prove:
that a real model reasons well. That is measured by evals/investigation_reliability.py.
"""

import json

import pytest

from sentinel.domain.system import LlmStatus
from sentinel.investigation.bundle import build_bundle, fact_index
from sentinel.investigation.prompt import PROMPT_VERSION, build_prompt
from sentinel.investigation.providers.mock import MockProvider
from sentinel.investigation.validator import ValidationFailure, validate_output
from sentinel.services.investigation import InvestigationService
from sentinel.store.sqlite import SqliteStore
from tests.investigation_cases import (
    CASES,
    case_a_low_credits_and_5xx,
    case_b_5xx_with_normal_cpu,
    case_c_low_credits_only,
    case_d_status_check_failing,
    case_e_gaps_and_no_deployment_data,
)

# The first real-provider reply for INC-0001 (openai/gpt-oss-20b, prompt investigation-v1),
# as stored. F1 = low credit balance, F2 = 5xx rate: the same ids as case A.
INC_0001_REPLY = {
    "summary": "CPU credits dropped to zero and 5xx errors spiked, suggesting CPU throttling "
    "caused the errors.",
    "hypotheses": [
        {
            "id": "H1",
            "statement": "CPU credit exhaustion caused CPU throttling, leading to 5xx errors.",
            "confidence": "high",
            "cites": ["F1", "F2"],
        },
        {
            "id": "H2",
            "statement": "5xx errors were caused by an unrelated application issue.",
            "confidence": "low",
            "cites": ["F2"],
        },
    ],
    "next_checks": [
        {
            "id": "C1",
            "description": "Review CPU credit usage trend and instance type to confirm throttling.",
            "cites": ["F1"],
        }
    ],
    "remediation": [
        {
            "id": "R1",
            "description": "Add horizontal scaling to distribute load and reduce 5xx spikes.",
            "requires_human": True,
            "cites": ["F2"],
        }
    ],
    "limitations": ["No application logs or detailed CPU usage data are available."],
}

CAUTIOUS_REPLY = {
    "summary": "A low credit balance and a 5xx spike co-occurred; the cause is not determined.",
    "hypotheses": [
        {
            "id": "H1",
            "statement": "The application returns errors for reasons the metrics do not show.",
            "confidence": "medium",
            "cites": ["F2", "F3"],
        },
        {
            "id": "H2",
            "statement": "CPU throttling contributes: unlikely, as CPU utilization is near 1%.",
            "confidence": "low",
            "cites": ["F1", "F2", "F3"],
        },
    ],
    "next_checks": [
        {"id": "C1", "description": "Read the application logs for the error.", "cites": ["F2"]}
    ],
    "remediation": [],
    "limitations": ["No application logs or deployment data in the evidence."],
}


def _mock(incident):
    bundle = build_bundle(incident)
    reply = MockProvider().complete(build_prompt(bundle))
    findings = validate_output(reply, fact_index(bundle))
    return bundle, findings


class _Scripted:
    name = "scripted"
    model = "scripted-1"

    def __init__(self, *replies):
        self.replies = [json.dumps(r) for r in replies]
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def _run(incident, provider, clock):
    store = SqliteStore(":memory:")
    store.add_incident(incident)
    status = LlmStatus(provider=provider.name, model=provider.model, configured=True)
    return store, InvestigationService(store, provider, status, clock).run(incident.id)


# --- every case: told the truth, mock stays within its evidence -------------------------


@pytest.mark.parametrize("name", CASES)
def test_mock_never_rates_high_and_every_remediation_is_conditional(name):
    _, findings = _mock(CASES[name]())
    assert all(h.confidence != "high" for h in findings.hypotheses)
    assert all(r.description.startswith("If ") for r in findings.remediation)
    assert all(r.requires_human for r in findings.remediation)


@pytest.mark.parametrize("name", CASES)
def test_the_mock_never_joins_breaches_of_different_rules(name):
    bundle, findings = _mock(CASES[name]())
    facts = fact_index(bundle)
    for h in findings.hypotheses:
        rules = {facts[c].rule_id for c in h.cites if facts[c].kind == "threshold_breach"}
        assert len(rules) <= 1, h


def test_prompt_states_the_reasoning_rules():
    prompt = " ".join(build_prompt(build_bundle(case_a_low_credits_and_5xx())).split())
    assert PROMPT_VERSION == "investigation-v2"
    for rule in (
        "Correlation is not causation",
        "A low CPU credit balance alone does not show CPU throttling",
        "An elevated 5xx rate alone does not show",
        'Do not turn "low" into "zero"',
        'at most "medium"',
        "confirm or refute",
        "Do not recommend scaling, larger instances or other costly changes",
        "say so in the summary",
    ):
        assert rule in prompt, rule


# --- A. low credits + high 5xx, no proof of a link (INC-0001) ---------------------------


def test_a_the_recorded_inc_0001_reply_is_now_rejected():
    bundle = build_bundle(case_a_low_credits_and_5xx())
    with pytest.raises(ValidationFailure) as info:
        validate_output(json.dumps(INC_0001_REPLY), fact_index(bundle))
    assert info.value.reason == "confidence_unsupported"


def test_a_the_check_reads_confidence_and_citations_not_wording():
    # The same causal sentence, stated as a tentative hypothesis, passes: the validator is
    # not a phrase filter. Whether the wording overclaims is left to the prompt and the
    # human reader; the "Inferred" styling in the console marks it as such.
    reply = json.loads(json.dumps(INC_0001_REPLY))
    reply["hypotheses"][0]["confidence"] = "medium"
    bundle = build_bundle(case_a_low_credits_and_5xx())
    assert validate_output(json.dumps(reply), fact_index(bundle)).hypotheses[0].cites == [
        "F1",
        "F2",
    ]


def test_a_a_rejected_overclaim_gets_one_retry_and_the_cautious_answer_is_kept(clock):
    incident = case_a_low_credits_and_5xx()
    provider = _Scripted(INC_0001_REPLY, CAUTIOUS_REPLY)
    store, result = _run(incident, provider, clock)
    inv = result.investigation
    assert inv.status == "completed" and inv.attempts == 2
    assert "confidence_unsupported" in provider.prompts[1]
    assert "R-5XX, R-CPU-CREDIT" in provider.prompts[1]
    assert [h.confidence for h in inv.findings.hypotheses] == ["medium", "low"]
    assert store.get_incident(incident.id).severity == incident.severity  # untouched


def test_a_an_overclaim_twice_fails_and_nothing_is_kept(clock):
    _, result = _run(case_a_low_credits_and_5xx(), _Scripted(INC_0001_REPLY, INC_0001_REPLY), clock)
    inv = result.investigation
    assert inv.status == "failed" and inv.findings is None
    assert inv.error.code == "confidence_unsupported"


def test_a_the_bundle_says_deployments_were_not_collected_and_cpu_is_normal():
    bundle = build_bundle(case_a_low_credits_and_5xx())
    scope = bundle["evidence_scope"]
    assert scope["deployment_events_collected"] is False
    assert scope["not_in_evidence"][0].startswith("deployment and other change events")
    assert any("log lines" in item for item in scope["not_in_evidence"])
    normal = {f["rule_id"] for f in bundle["facts"] if f["kind"] == "within_normal"}
    assert "R-CPU-SAT" in normal  # the counter-evidence to "throttling" is in the bundle


def test_a_the_mock_reports_co_occurrence_not_a_cause():
    _, findings = _mock(case_a_low_credits_and_5xx())
    assert any("co-occur" in limit for limit in findings.limitations)
    assert any("not collected" in limit for limit in findings.limitations)
    assert "deployment events not collected" in findings.summary


# --- B. high 5xx, normal CPU ------------------------------------------------------------


def test_b_the_mock_offers_no_cpu_explanation():
    bundle, findings = _mock(case_b_5xx_with_normal_cpu())
    facts = fact_index(bundle)
    assert all(facts[c].rule_id == "R-5XX" for h in findings.hypotheses for c in h.cites)
    assert not any("cpu" in h.statement.lower() for h in findings.hypotheses)


# --- C. low credits, no error-rate evidence ---------------------------------------------


def test_c_the_mock_claims_neither_impact_nor_throttling():
    _, findings = _mock(case_c_low_credits_only())
    texts = " ".join([findings.summary, *(h.statement for h in findings.hypotheses)]).lower()
    assert "error" not in texts and "outage" not in texts and "user" not in texts
    assert "do not show whether demand exceeds" in texts


# --- D. direct evidence: a confident diagnosis must stay possible -----------------------


def test_d_a_high_confidence_diagnosis_from_direct_evidence_is_kept(clock):
    reply = {
        "summary": "The EC2 status check has been failing for 10 minutes.",
        "hypotheses": [
            {
                "id": "H1",
                "statement": "The instance or its host is impaired at the EC2 level.",
                "confidence": "high",
                "cites": ["F1", "F2", "F4"],  # the failing check, with CPU and memory normal
            }
        ],
        "next_checks": [
            {"id": "C1", "description": "See which status check fails.", "cites": ["F1"]}
        ],
    }
    _, result = _run(case_d_status_check_failing(), _Scripted(reply), clock)
    inv = result.investigation
    assert inv.status == "completed" and inv.attempts == 1
    assert inv.findings.hypotheses[0].confidence == "high"


# --- E. gaps, no deployment data, conflicting picture -----------------------------------


def test_e_high_confidence_resting_on_data_gaps_is_rejected():
    incident = case_e_gaps_and_no_deployment_data()
    gaps = [f.id for f in incident.facts if f.kind == "data_gap"]
    assert len(gaps) == 2
    reply = {
        "summary": "Memory exhaustion caused the errors.",
        "hypotheses": [
            {"id": "H1", "statement": "Memory ran out.", "confidence": "high", "cites": gaps}
        ],
    }
    with pytest.raises(ValidationFailure) as info:
        validate_output(json.dumps(reply), fact_index(build_bundle(incident)))
    assert info.value.reason == "confidence_unsupported"


def test_e_the_mock_names_the_gaps_and_invents_no_deployment():
    bundle, findings = _mock(case_e_gaps_and_no_deployment_data())
    assert bundle["evidence_scope"]["fact_kinds"]["data_gap"].startswith("not observed")
    assert not any("deploy" in h.statement.lower() for h in findings.hypotheses)
    assert any("data gaps" in limit for limit in findings.limitations)
    assert any("cannot be ruled out" in limit for limit in findings.limitations)
    gap_checks = [c for c in findings.next_checks if "missing data source" in c.description]
    assert len(gap_checks) == 2
