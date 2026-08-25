
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from apps.worker.consumers.case_processing import process_case_event
from models.enums import CaseState, CaseType, EventType, ProcessingStatus, RecoveryAction, RiskLevel, VerificationOutcome
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.payments.simulation_provider import SimulationProvider
from services.payments.verification import run_verification
from services.policy.config_repository import ensure_default_global_config
from services.recovery.case_orchestrator import ScriptedDecision
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine
from tests.integration.test_payment_verification_flow import (
    drive_case_to_verification_pending,
    insert_payment_event,
)


def make_received_case(sm, *, failure_code="bank_timeout", amount=Decimal("1000.00"), payment_id="pay_worker"):
    return sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_1",
        customer_id="cust_1", payment_id=payment_id, order_id="order_worker", amount=amount, currency="INR",
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
    session.add(PaymentEvent(
        event_id=raw.razorpay_event_id, correlation_id=uuid.uuid4(), case_id=case.id,
        payment_id=case.payment_id, order_id=case.order_id, event_type=EventType.PAYMENT_CAPTURED,
        amount=case.amount, currency="INR", payment_method="upi",
        timestamp=datetime.now(timezone.utc), raw_payload_reference=raw.id,
        received_at=datetime.now(timezone.utc), processing_status=ProcessingStatus.PROCESSED,
    ))
    session.flush()


def test_a_newly_received_case_is_driven_through_the_full_pipeline(db_session, redis_client):
    """This is the exact gap the queue/worker exist to close: a case
    sitting at RECEIVED (as webhook ingestion alone leaves it) actually
    gets processed, the same way run_case_pipeline already proves it can
    be — just reached via the message the worker consumes instead of a
    direct call."""
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = make_received_case(sm)
    insert_captured_event(db_session, case)
    assert case.current_state is CaseState.RECEIVED

    result = process_case_event(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        reconciliation_needed=False,
        scripted_decision=ScriptedDecision(
            action=RecoveryAction.RETRY, reason="transient timeout", confidence=0.9,
            expected_recovery_value=900.0, risk_level=RiskLevel.LOW.value,
        ),
    )

    assert result is not None
    assert result.verification_result.outcome.value == "RECOVERED"
    assert result.case.current_state is CaseState.RECOVERED


def test_a_reconciliation_message_re_verifies_a_failed_case(db_session, redis_client):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)
    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_FAILED)
    first = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )
    assert first.outcome is VerificationOutcome.FAILED
    assert case.current_state is CaseState.FAILED

    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_CAPTURED)

    result = process_case_event(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        reconciliation_needed=True,
    )

    assert result is not None
    assert result.verification_result.outcome is VerificationOutcome.RECOVERED
    assert result.case.current_state is CaseState.RECOVERED


def test_reconciliation_message_for_a_case_not_in_failed_is_a_no_op(db_session, redis_client):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = make_received_case(sm)
    assert case.current_state is CaseState.RECEIVED

    result = process_case_event(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        reconciliation_needed=True,
    )

    assert result is None
    assert case.current_state is CaseState.RECEIVED


def test_a_second_message_for_an_already_advanced_case_is_a_no_op(db_session, redis_client):
    """Simulates a redelivered or duplicate queue message — must never
    re-run the pipeline against a case that already moved past RECEIVED,
    since run_case_pipeline's own state-machine transitions would reject
    it anyway; this should be a clean no-op, not an error."""
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = make_received_case(sm)
    insert_captured_event(db_session, case)

    first = process_case_event(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        reconciliation_needed=False,
        scripted_decision=ScriptedDecision(
            action=RecoveryAction.RETRY, reason="transient timeout", confidence=0.9,
            expected_recovery_value=900.0, risk_level=RiskLevel.LOW.value,
        ),
    )
    assert first.case.current_state is CaseState.RECOVERED

    second = process_case_event(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        reconciliation_needed=False,
    )
    assert second is None
    assert case.current_state is CaseState.RECOVERED
