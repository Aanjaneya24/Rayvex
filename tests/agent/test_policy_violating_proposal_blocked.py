
from models.enums import CaseState, PolicyVerdictType
from services.agent.orchestrator import RecoveryAgentOrchestrator
from services.policy.config_repository import ensure_default_global_config
from services.recovery.action_gate import check_action_before_execution
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine
from tests.agent.helpers import (
    drive_case_to_action_pending,
    fake_model_with_responses,
    record_decision_call,
)


def test_confident_agent_proposal_to_blind_retry_insufficient_funds_is_still_blocked(
    db_session, redis_client
):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="insufficient_funds", amount=1000)

    decision_json = (
        '{"action": "RETRY", "reason": "Customer likely has funds now, retry '
        'immediately", "confidence": 0.97, "expected_recovery_value": 950, '
        '"risk_level": "LOW"}'
    )
    model = fake_model_with_responses(record_decision_call(decision_json))
    orchestrator = RecoveryAgentOrchestrator(llm=model)

    decision = orchestrator.propose(
        db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id,
    )
    assert decision.action.value == "RETRY"
    assert decision.confidence == 0.97
    assert case.current_state is CaseState.ACTION_PENDING

    result = check_action_before_execution(
        db_session, redis_client, case_id=case.id, proposed_action=decision.action,
        correlation_id=case.correlation_id, risk_score=0.1,
    )

    assert result.approved is False
    assert result.policy_decision.verdict_type is PolicyVerdictType.DENY
    assert result.policy_decision.rule_id == "prohibited_retry_failure_code"
    assert case.current_state is CaseState.STOPPED
    assert result.policy_decision.context_snapshot["proposed_action"] == "RETRY"


def test_confident_agent_proposal_after_retry_limit_exhausted_is_still_blocked(
    db_session, redis_client
):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=100)

    for _ in range(3):
        correlation_id = case.correlation_id
        sm.transition(case.id, to_state=CaseState.ACTION_EXECUTED, reason="RETRY executed",
                       actor="system:action_executor", correlation_id=correlation_id,
                       evidence={"action": "RETRY"})
        sm.transition(case.id, to_state=CaseState.VERIFICATION_PENDING, reason="awaiting verification",
                       actor="system:action_executor", correlation_id=correlation_id)
        sm.transition(case.id, to_state=CaseState.FAILED, reason="verification found no success",
                       actor="system:verification", correlation_id=correlation_id)
        sm.transition(case.id, to_state=CaseState.DECISION, reason="attempting again",
                       actor="system:recovery", correlation_id=correlation_id)
        sm.transition(case.id, to_state=CaseState.ACTION_PENDING, reason="RETRY proposed again",
                       actor="agent:llm", correlation_id=correlation_id)

    decision_json = (
        '{"action": "RETRY", "reason": "One more retry should work", '
        '"confidence": 0.8, "expected_recovery_value": 80, "risk_level": "LOW"}'
    )
    model = fake_model_with_responses(record_decision_call(decision_json))
    orchestrator = RecoveryAgentOrchestrator(llm=model)
    decision = orchestrator.propose(
        db_session, redis_client, case_id=case.id, correlation_id=case.correlation_id,
    )

    result = check_action_before_execution(
        db_session, redis_client, case_id=case.id, proposed_action=decision.action,
        correlation_id=case.correlation_id, risk_score=0.1,
    )

    assert result.approved is False
    assert result.policy_decision.rule_id == "max_retry_count_exceeded"
    assert case.current_state is CaseState.STOPPED
