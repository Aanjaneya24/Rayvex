
import json

import pytest
from sqlalchemy import select

from models.agent_decision import AgentDecision
from services.agent.exceptions import MalformedAgentOutputError
from services.agent.orchestrator import RecoveryAgentOrchestrator
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine
from tests.agent.helpers import (
    drive_case_to_action_pending,
    fake_model_with_responses,
    record_decision_call,
)


def test_malformed_json_is_rejected_and_nothing_is_persisted(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=100)

    model = fake_model_with_responses(record_decision_call("this is not valid json at all"))
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    with pytest.raises(MalformedAgentOutputError):
        orchestrator.propose(db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id)

    persisted = db_session.execute(select(AgentDecision).where(AgentDecision.case_id == case.id)).all()
    assert persisted == []


def test_missing_required_field_is_rejected(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=100)

    malformed = json.dumps({
        "action": "RETRY", "reason": "looks fine",
        "expected_recovery_value": 100, "risk_level": "LOW",
    })
    model = fake_model_with_responses(record_decision_call(malformed))
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    with pytest.raises(MalformedAgentOutputError):
        orchestrator.propose(db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id)


def test_unsupported_action_is_rejected_never_coerced(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=100)

    malformed = json.dumps({
        "action": "RETRY_NOW", "reason": "should retry immediately",
        "confidence": 0.9, "expected_recovery_value": 100, "risk_level": "LOW",
    })
    model = fake_model_with_responses(record_decision_call(malformed))
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    with pytest.raises(MalformedAgentOutputError):
        orchestrator.propose(db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id)


def test_model_that_never_calls_record_decision_is_rejected(db_session, redis_client):
    from langchain_core.messages import AIMessage

    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=100)

    model = fake_model_with_responses(AIMessage(content="I am thinking about this case."))
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    with pytest.raises(MalformedAgentOutputError):
        orchestrator.propose(db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id)
