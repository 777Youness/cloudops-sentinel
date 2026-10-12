"""The validator: one test per rejection reason, plus what it accepts."""

import json

import pytest

from sentinel.investigation.validator import ValidationFailure, validate_output

FACTS = {"F1", "F2", "F3"}


def _reply(**overrides):
    reply = {
        "summary": "CPU saturation followed a deployment.",
        "hypotheses": [
            {
                "id": "H1",
                "statement": "The deployment increased CPU demand.",
                "confidence": "medium",
                "cites": ["F1", "F2"],
            }
        ],
        "next_checks": [{"id": "C1", "description": "Compare request rate.", "cites": ["F1"]}],
        "remediation": [
            {
                "id": "R1",
                "description": "Consider rolling back the deployment.",
                "requires_human": True,
                "cites": ["F2"],
            }
        ],
        "limitations": ["Memory was not collected."],
    }
    reply.update(overrides)
    return json.dumps(reply)


def _reason(text, facts=FACTS):
    with pytest.raises(ValidationFailure) as info:
        validate_output(text, facts)
    return info.value.reason


# --- accepted --------------------------------------------------------------------------


def test_accepts_a_valid_reply():
    findings = validate_output(_reply(), FACTS)
    assert findings.hypotheses[0].cites == ["F1", "F2"]
    assert findings.remediation[0].requires_human is True


def test_unwraps_a_single_fenced_json_block():
    assert validate_output(f"```json\n{_reply()}\n```", FACTS).summary


# --- one test per rejection reason ------------------------------------------------------


def test_not_json():
    assert _reason("The root cause is probably CPU.") == "not_json"


def test_not_an_object():
    assert _reason(json.dumps([{"id": "H1"}])) == "not_json"


def test_forbidden_field_severity():
    assert _reason(_reply(severity="critical")) == "forbidden_field"


def test_forbidden_field_nested_command():
    remediation = [
        {
            "id": "R1",
            "description": "Restart the service.",
            "requires_human": True,
            "cites": ["F1"],
            "command": "systemctl restart app",
        }
    ]
    assert _reason(_reply(remediation=remediation)) == "forbidden_field"


def test_remediation_not_human():
    remediation = [
        {"id": "R1", "description": "Roll back.", "requires_human": False, "cites": ["F1"]}
    ]
    assert _reason(_reply(remediation=remediation)) == "remediation_not_human"


def test_schema_invalid_unknown_field():
    assert _reason(_reply(root_cause="CPU")) == "schema_invalid"


def test_schema_invalid_bad_confidence():
    hypotheses = [{"id": "H1", "statement": "x", "confidence": "certain", "cites": ["F1"]}]
    assert _reason(_reply(hypotheses=hypotheses)) == "schema_invalid"


def test_schema_invalid_too_many_items():
    hypotheses = [
        {"id": f"H{i}", "statement": "x", "confidence": "low", "cites": ["F1"]} for i in range(6)
    ]
    assert _reason(_reply(hypotheses=hypotheses)) == "schema_invalid"


def test_no_hypotheses():
    assert _reason(_reply(hypotheses=[])) == "no_hypotheses"


def test_missing_citation_on_hypothesis():
    hypotheses = [{"id": "H1", "statement": "x", "confidence": "low", "cites": []}]
    assert _reason(_reply(hypotheses=hypotheses)) == "missing_citation"


def test_missing_citation_on_next_check():
    checks = [{"id": "C1", "description": "Look at logs.", "cites": []}]
    assert _reason(_reply(next_checks=checks)) == "missing_citation"


def test_unknown_fact():
    hypotheses = [{"id": "H1", "statement": "x", "confidence": "low", "cites": ["F1", "F9"]}]
    with pytest.raises(ValidationFailure) as info:
        validate_output(_reply(hypotheses=hypotheses), FACTS)
    assert info.value.reason == "unknown_fact"
    assert "F9" in info.value.detail  # the retry tells the model exactly what was wrong


def test_duplicate_id():
    checks = [{"id": "H1", "description": "Compare request rate.", "cites": ["F1"]}]
    assert _reason(_reply(next_checks=checks)) == "duplicate_id"


def test_text_too_long():
    assert _reason(_reply(summary="x" * 301)) == "text_too_long"


@pytest.mark.parametrize(
    "description",
    [
        "Run `systemctl restart app` on the host.",
        "$ reboot",
        "Use sudo reboot on the instance.",
        "Clean up with rm -rf /tmp/cache.",
        "Call aws ec2 reboot-instances for the instance.",
    ],
)
def test_command_in_text(description):
    remediation = [
        {"id": "R1", "description": description, "requires_human": True, "cites": ["F1"]}
    ]
    assert _reason(_reply(remediation=remediation)) == "command_in_text"


def test_plain_words_mentioning_aws_are_fine():
    remediation = [
        {
            "id": "R1",
            "description": "In the AWS console, review the instance's recent changes.",
            "requires_human": True,
            "cites": ["F1"],
        }
    ]
    assert validate_output(_reply(remediation=remediation), FACTS).remediation
