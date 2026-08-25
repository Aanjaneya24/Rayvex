
import pytest

from models.enums import RecoveryAction, RiskLevel
from services.agent.exceptions import MalformedAgentOutputError
from services.agent.validation import parse_agent_decision

VALID_DECISION = {
    "action": "RETRY",
    "reason": "Transient timeout with no previous retry",
    "confidence": 0.91,
    "expected_recovery_value": 4210,
    "risk_level": "LOW",
}


def test_accepts_the_prd_example_verbatim():
    decision = parse_agent_decision(VALID_DECISION)
    assert decision.action is RecoveryAction.RETRY
    assert decision.confidence == 0.91
    assert decision.expected_recovery_value == 4210
    assert decision.risk_level is RiskLevel.LOW


def test_accepts_json_string_form_too():
    import json

    decision = parse_agent_decision(json.dumps(VALID_DECISION))
    assert decision.action is RecoveryAction.RETRY


def test_rejects_not_json_at_all():
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision("I think we should retry this payment.")


def test_rejects_a_json_array_instead_of_an_object():
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision("[1, 2, 3]")


@pytest.mark.parametrize("missing_field", list(VALID_DECISION.keys()))
def test_rejects_missing_required_field(missing_field):
    payload = {k: v for k, v in VALID_DECISION.items() if k != missing_field}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


def test_rejects_unsupported_action_string():
    payload = {**VALID_DECISION, "action": "DELETE_CUSTOMER_ACCOUNT"}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


def test_rejects_action_not_in_the_prd_64_allowed_set_even_if_plausible_sounding():
    payload = {**VALID_DECISION, "action": "RETRY_PAYMENT"}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


def test_rejects_unsupported_risk_level():
    payload = {**VALID_DECISION, "risk_level": "CRITICAL"}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01, 2.0, -5])
def test_rejects_confidence_outside_zero_to_one(bad_confidence):
    payload = {**VALID_DECISION, "confidence": bad_confidence}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


def test_rejects_empty_reason():
    payload = {**VALID_DECISION, "reason": ""}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


def test_rejects_wrong_type_for_confidence():
    payload = {**VALID_DECISION, "confidence": "very confident"}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


def test_rejects_extra_undeclared_fields():
    payload = {**VALID_DECISION, "override_policy": True}
    with pytest.raises(MalformedAgentOutputError):
        parse_agent_decision(payload)


def test_accepts_every_allowed_action_and_risk_level():
    for action in RecoveryAction:
        for risk_level in RiskLevel:
            payload = {**VALID_DECISION, "action": action.value, "risk_level": risk_level.value}
            decision = parse_agent_decision(payload)
            assert decision.action is action
            assert decision.risk_level is risk_level


def test_expected_recovery_value_may_be_negative():
    payload = {**VALID_DECISION, "expected_recovery_value": -37.5}
    decision = parse_agent_decision(payload)
    assert decision.expected_recovery_value == -37.5


def test_error_carries_the_raw_output_for_audit_logging():
    try:
        parse_agent_decision("not json")
    except MalformedAgentOutputError as exc:
        assert exc.raw_output == "not json"
    else:
        pytest.fail("expected MalformedAgentOutputError")
