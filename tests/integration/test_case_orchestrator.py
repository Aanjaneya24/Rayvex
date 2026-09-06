
import uuid
from decimal import Decimal

from models.enums import CaseState, CaseType, EventType, ProcessingStatus, RecoveryAction, RiskLevel
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.policy.config_repository import ensure_default_global_config
from services.recovery.case_orchestrator import ScriptedDecision, run_case_pipeline
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine


def make_received_case(sm, *, failure_code="bank_timeout", amount=Decimal("1000.00"), payment_id="pay_x"):
    return sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_1",
        customer_id="cust_1", payment_id=payment_id, order_id="order_x", amount=amount, currency="INR",
        payment_method="upi", failure_code=failure_code, failure_reason="payment_failed",
        reason="payment.failed webhook received", actor="system:ingestion",
    )


def insert_captured_event(session, case):
    raw = RawWebhookEvent(
        correlation_id=uuid.uuid4(), razorpay_event_id=f"evt_{uuid.uuid4()}",
        event_type="payment.captured", raw_payload={}, signature_valid=True,
        processing_status=ProcessingStatus.PROCESSED,
    )
    session.add(raw)
    session.flush()
    from datetime import datetime, timezone

    session.add(PaymentEvent(
        event_id=raw.razorpay_event_id, correlation_id=uuid.uuid4(), case_id=case.id,
        payment_id=case.payment_id, order_id=case.order_id, event_type=EventType.PAYMENT_CAPTURED,
        amount=case.amount, currency="INR", payment_method="upi",
        timestamp=datetime.now(timezone.utc), raw_payload_reference=raw.id,
        received_at=datetime.now(timezone.utc), processing_status=ProcessingStatus.PROCESSED,
    ))
    session.flush()


def test_full_pipeline_reaches_recovered_with_scripted_decision_and_simulation_provider(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = make_received_case(sm)
    insert_captured_event(db_session, case)

    result = run_case_pipeline(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        scripted_decision=ScriptedDecision(
            action=RecoveryAction.RETRY, reason="transient timeout", confidence=0.9,
            expected_recovery_value=900.0, risk_level=RiskLevel.LOW.value,
        ),
    )

    assert result.gate_result.approved is True
    assert result.verification_result.outcome.value == "RECOVERED"
    assert result.case.current_state is CaseState.RECOVERED


def test_full_pipeline_stops_at_the_gate_for_a_policy_violating_scripted_decision(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = make_received_case(sm, failure_code="insufficient_funds")

    result = run_case_pipeline(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        scripted_decision=ScriptedDecision(
            action=RecoveryAction.RETRY, reason="retry anyway", confidence=0.9,
            expected_recovery_value=900.0, risk_level=RiskLevel.LOW.value,
        ),
    )

    assert result.gate_result.approved is False
    assert result.verification_result is None
    assert result.case.current_state is CaseState.STOPPED


def test_pipeline_records_the_scripted_decision_as_an_agent_decision_row(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = make_received_case(sm)
    insert_captured_event(db_session, case)

    run_case_pipeline(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        scripted_decision=ScriptedDecision(
            action=RecoveryAction.RETRY, reason="transient timeout", confidence=0.9,
            expected_recovery_value=900.0, risk_level=RiskLevel.LOW.value,
        ),
    )

    from models.agent_decision import AgentDecision

    row = db_session.query(AgentDecision).filter_by(case_id=case.id).one()
    assert row.model_backend == "scripted:no-llm-configured"


def test_pipeline_uses_an_injected_action_executor_not_just_the_default(db_session, redis_client):
    """Confirms the executor is genuinely swappable, not an unused
    parameter: by injecting one that reports a real (non-simulated)
    execution and checking that outcome actually reaches the transition
    the pipeline writes."""
    from models.enums import RecoveryAction as _RecoveryAction
    from services.recovery.action_executor import ActionExecutionResult

    class FakeRealExecutor:
        def execute(self, action, *, case_id):
            return ActionExecutionResult(action=action, simulated=False, detail="executed for real (test double)")

    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = make_received_case(sm)
    insert_captured_event(db_session, case)

    run_case_pipeline(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        executor=FakeRealExecutor(),
        scripted_decision=ScriptedDecision(
            action=_RecoveryAction.RETRY, reason="transient timeout", confidence=0.9,
            expected_recovery_value=900.0, risk_level=RiskLevel.LOW.value,
        ),
    )

    executed_transition = next(t for t in sm.history(case.id) if t.to_state is CaseState.ACTION_EXECUTED)
    assert executed_transition.actor == "system:action_executor"
    assert executed_transition.evidence["simulated"] is False
    assert executed_transition.reason == "executed for real (test double)"
