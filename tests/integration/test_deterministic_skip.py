
import uuid
from decimal import Decimal

from models.agent_decision import AgentDecision
from models.enums import CaseState, CaseType, RecoveryAction
from services.policy.config_repository import ensure_default_global_config
from services.policy.redis_guards import record_action_attempt
from services.recovery.case_orchestrator import (
    DETERMINISTIC_SKIP_MODEL_BACKEND,
    ScriptedDecision,
    check_deterministic_stop,
    run_case_pipeline,
)
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine


def _create_case(sm, *, customer_id, payment_id):
    return sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_skip",
        customer_id=customer_id, payment_id=payment_id, order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )


def test_retry_limit_exhausted_is_detected_by_the_pure_check(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = _create_case(sm, customer_id="cust_skip_retry", payment_id="pay_skip_retry")

    for to_state in [CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK, CaseState.DECISION]:
        sm.transition(case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
                       correlation_id=uuid.uuid4())

    for attempt in range(3):
        sm.transition(case.id, to_state=CaseState.ACTION_PENDING, reason="RETRY proposed",
                       actor="agent:scripted", correlation_id=uuid.uuid4())
        sm.transition(case.id, to_state=CaseState.ACTION_EXECUTED, reason="RETRY executed (simulated)",
                       actor="system:simulated_action_executor", correlation_id=uuid.uuid4(),
                       evidence={"action": RecoveryAction.RETRY.value})
        sm.transition(case.id, to_state=CaseState.VERIFICATION_PENDING, reason="awaiting confirmation",
                       actor="system:pipeline", correlation_id=uuid.uuid4())
        sm.transition(case.id, to_state=CaseState.FAILED, reason="verification found no successful payment state",
                       actor="system:verification", correlation_id=uuid.uuid4())
        if attempt < 2:
            sm.transition(case.id, to_state=CaseState.DECISION, reason="attempting again",
                           actor="system:recovery", correlation_id=uuid.uuid4())

    sm.transition(case.id, to_state=CaseState.DECISION, reason="4th attempt decision", actor="system:pipeline",
                  correlation_id=uuid.uuid4())
    case = sm.get_case(case.id)
    reason = check_deterministic_stop(db_session, redis_client, case=case, risk_score=0.1, current_hour=12)

    assert reason is not None
    assert "3" in reason


def test_run_case_pipeline_skips_llm_when_customer_already_has_suspicious_velocity(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    customer_id = "cust_skip_velocity_pipeline"
    for _ in range(10):
        record_action_attempt(
            redis_client, case_id=uuid.uuid4(), customer_id=customer_id,
            cooldown_seconds=1, velocity_window_seconds=3600,
        )

    sm = RecoveryStateMachine(db_session)
    case = _create_case(sm, customer_id=customer_id, payment_id="pay_skip_velocity_pipeline")

    result = run_case_pipeline(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(), current_hour=12,
    )

    assert result.decision.action == RecoveryAction.STOP
    agent_decision = (
        db_session.query(AgentDecision).filter_by(case_id=case.id).order_by(AgentDecision.created_at.desc()).first()
    )
    assert agent_decision.model_backend == DETERMINISTIC_SKIP_MODEL_BACKEND
    assert agent_decision.llm_call_count == 0
    assert agent_decision.total_latency_ms == 0
    assert agent_decision.estimated_cost_usd == 0.0


def test_normal_case_without_deterministic_conditions_does_not_skip(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = _create_case(sm, customer_id="cust_normal_skip_check", payment_id="pay_normal_skip_check")

    reason = check_deterministic_stop(db_session, redis_client, case=case, risk_score=0.1, current_hour=12)
    assert reason is None

    result = run_case_pipeline(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(), current_hour=12,
        scripted_decision=ScriptedDecision(
            action=RecoveryAction.RETRY, reason="transient timeout, retry",
            confidence=0.8, expected_recovery_value=500.0, risk_level="LOW",
        ),
    )
    assert result.decision.action == RecoveryAction.RETRY
    agent_decision = (
        db_session.query(AgentDecision).filter_by(case_id=case.id).order_by(AgentDecision.created_at.desc()).first()
    )
    assert agent_decision.model_backend != DETERMINISTIC_SKIP_MODEL_BACKEND
