
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from models.enums import CaseState, CaseType, EventType, ProcessingStatus, ProviderMode
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.payments.simulation_provider import SimulationProvider
from services.recovery.state_machine import RecoveryStateMachine


def make_case(sm):
    return sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_1",
        customer_id="cust_1", payment_id="pay_sim_1", order_id="order_sim_1",
        amount=Decimal("750.00"), currency="INR", payment_method="card",
        failure_code="card_declined", failure_reason="payment_failed",
        reason="payment.failed webhook received", actor="system:ingestion",
    )


def insert_event(session, case, event_type: EventType, amount=None):
    raw = RawWebhookEvent(
        correlation_id=uuid.uuid4(), razorpay_event_id=f"evt_{uuid.uuid4()}",
        event_type=event_type.value, raw_payload={}, signature_valid=True,
        processing_status=ProcessingStatus.PROCESSED,
    )
    session.add(raw)
    session.flush()
    event = PaymentEvent(
        event_id=raw.razorpay_event_id, correlation_id=uuid.uuid4(), case_id=case.id,
        payment_id=case.payment_id, order_id=case.order_id, event_type=event_type,
        amount=amount if amount is not None else case.amount, currency="INR",
        payment_method="card", timestamp=datetime.now(timezone.utc),
        raw_payload_reference=raw.id, received_at=datetime.now(timezone.utc),
        processing_status=ProcessingStatus.PROCESSED,
        failure_code=case.failure_code if event_type is EventType.PAYMENT_FAILED else None,
        failure_reason=case.failure_reason if event_type is EventType.PAYMENT_FAILED else None,
    )
    session.add(event)
    session.flush()
    return event


def test_get_payment_with_no_events_reports_created_honestly(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    provider = SimulationProvider(db_session)

    record = provider.get_payment(case.payment_id)

    assert record.mode is ProviderMode.SIMULATION_MODE
    assert record.status == "created"
    assert record.raw_response["simulated_from_event_id"] is None


def test_get_payment_reflects_latest_event(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    provider = SimulationProvider(db_session)

    insert_event(db_session, case, EventType.PAYMENT_FAILED)
    first = provider.get_payment(case.payment_id)
    assert first.status == "failed"
    assert first.error_code == "card_declined"

    insert_event(db_session, case, EventType.PAYMENT_CAPTURED)
    second = provider.get_payment(case.payment_id)
    assert second.status == "captured"


def test_get_order_reports_paid_after_capture(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    provider = SimulationProvider(db_session)

    before = provider.get_order(case.order_id)
    assert before.status == "created"

    insert_event(db_session, case, EventType.PAYMENT_CAPTURED)
    after = provider.get_order(case.order_id)
    assert after.status == "paid"
    assert after.mode is ProviderMode.SIMULATION_MODE


def test_get_payment_status_is_a_lightweight_view_of_the_same_data(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    provider = SimulationProvider(db_session)
    insert_event(db_session, case, EventType.PAYMENT_AUTHORIZED)

    status = provider.get_payment_status(case.payment_id)

    assert status.mode is ProviderMode.SIMULATION_MODE
    assert status.status == "authorized"
    assert status.payment_id == case.payment_id
