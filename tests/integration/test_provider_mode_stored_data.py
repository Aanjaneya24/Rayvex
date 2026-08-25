
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from models.enums import CaseState, EventType, ProcessingStatus
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.payments.provider import ProviderMode, VerificationResult
from services.payments.simulation_provider import SimulationProvider
from services.payments.verification import run_verification
from services.recovery.state_machine import RecoveryStateMachine
from tests.integration.test_payment_verification_flow import drive_case_to_verification_pending


class FakeRazorpayLikeProvider:

    mode = ProviderMode.RAZORPAY_TEST_MODE

    def __init__(self, status: str, amount: Decimal):
        self._status = status
        self._amount = amount

    def verify_payment(self, payment_id: str) -> VerificationResult:
        return VerificationResult(
            mode=self.mode, payment_id=payment_id, status=self._status, amount=self._amount,
            currency="INR", raw_response={"id": payment_id, "status": self._status},
            fetched_at=datetime.now(timezone.utc),
        )


def _raw_mode_for_verification(session, verification_id) -> str:
    return session.execute(
        text("SELECT mode::text FROM payment_verifications WHERE id = :id"),
        {"id": verification_id},
    ).scalar_one()


def test_simulation_mode_is_stored_and_readable_via_raw_sql(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)

    raw = RawWebhookEvent(
        correlation_id=uuid.uuid4(), razorpay_event_id=f"evt_{uuid.uuid4()}",
        event_type="payment.captured", raw_payload={}, signature_valid=True,
        processing_status=ProcessingStatus.PROCESSED,
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(PaymentEvent(
        event_id=raw.razorpay_event_id, correlation_id=uuid.uuid4(), case_id=case.id,
        payment_id=case.payment_id, order_id=case.order_id, event_type=EventType.PAYMENT_CAPTURED,
        amount=case.amount, currency="INR", payment_method="upi",
        timestamp=datetime.now(timezone.utc), raw_payload_reference=raw.id,
        received_at=datetime.now(timezone.utc), processing_status=ProcessingStatus.PROCESSED,
    ))
    db_session.flush()

    result = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )

    assert result.verification.mode is ProviderMode.SIMULATION_MODE
    raw_mode = _raw_mode_for_verification(db_session, result.verification.id)
    assert raw_mode == "SIMULATION_MODE"


def test_razorpay_test_mode_is_stored_and_readable_via_raw_sql(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm, amount=Decimal("500.00"))

    provider = FakeRazorpayLikeProvider(status="captured", amount=Decimal("500.00"))
    result = run_verification(db_session, provider, case_id=case.id, correlation_id=uuid.uuid4())

    assert result.verification.mode is ProviderMode.RAZORPAY_TEST_MODE
    raw_mode = _raw_mode_for_verification(db_session, result.verification.id)
    assert raw_mode == "RAZORPAY_TEST_MODE"


def test_the_two_modes_are_never_the_same_stored_value(db_session):
    sm = RecoveryStateMachine(db_session)

    sim_case = drive_case_to_verification_pending(sm, payment_id="pay_sim")
    sim_result = run_verification(
        db_session, SimulationProvider(db_session), case_id=sim_case.id, correlation_id=uuid.uuid4(),
    )

    razorpay_case = drive_case_to_verification_pending(sm, payment_id="pay_real", amount=Decimal("1000.00"))
    razorpay_result = run_verification(
        db_session, FakeRazorpayLikeProvider(status="failed", amount=Decimal("1000.00")),
        case_id=razorpay_case.id, correlation_id=uuid.uuid4(),
    )

    sim_mode = _raw_mode_for_verification(db_session, sim_result.verification.id)
    razorpay_mode = _raw_mode_for_verification(db_session, razorpay_result.verification.id)

    assert sim_mode != razorpay_mode
    assert {sim_mode, razorpay_mode} == {"SIMULATION_MODE", "RAZORPAY_TEST_MODE"}


def test_mode_column_is_not_null_at_the_database_level(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO payment_verifications "
                "(id, case_id, correlation_id, payment_id, mode, outcome, raw_response, created_at) "
                "VALUES (gen_random_uuid(), :case_id, gen_random_uuid(), 'pay_x', NULL, "
                "'STILL_PENDING', '{}'::jsonb, now())"
            ),
            {"case_id": str(case.id)},
        )
