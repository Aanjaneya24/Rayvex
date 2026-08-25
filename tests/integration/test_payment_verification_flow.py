
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, CaseType, EventType, ProcessingStatus, VerificationOutcome
from models.payment_event import PaymentEvent
from models.payment_verification import PaymentVerification
from models.raw_webhook_event import RawWebhookEvent
from services.payments.provider import ProviderMode, VerificationResult
from services.payments.simulation_provider import SimulationProvider
from services.payments.verification import run_verification
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.state_machine import RecoveryStateMachine


class BrokenProvider:

    mode = ProviderMode.RAZORPAY_TEST_MODE

    def verify_payment(self, payment_id: str) -> VerificationResult:
        raise TimeoutError("simulated verification API timeout")


def drive_case_to_verification_pending(sm: RecoveryStateMachine, *, amount=Decimal("1000.00"), payment_id="pay_1"):
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_1",
        customer_id="cust_1", payment_id=payment_id, order_id="order_1", amount=amount,
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    for to_state in [
        CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION, CaseState.ACTION_PENDING, CaseState.ACTION_EXECUTED,
        CaseState.VERIFICATION_PENDING,
    ]:
        sm.transition(case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
                       correlation_id=uuid.uuid4())
    return case


def insert_payment_event(session, case, *, event_type: EventType, amount=None):
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
        payment_method="upi", timestamp=datetime.now(timezone.utc),
        raw_payload_reference=raw.id, received_at=datetime.now(timezone.utc),
        processing_status=ProcessingStatus.PROCESSED,
    )
    session.add(event)
    session.flush()
    return event


def test_verified_capture_reaches_recovered(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)
    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_CAPTURED)

    result = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )

    assert result.outcome is VerificationOutcome.RECOVERED
    assert case.current_state is CaseState.RECOVERED
    assert result.verification.mode is ProviderMode.SIMULATION_MODE
    assert result.transition.to_state is CaseState.RECOVERED


def test_verified_failure_reaches_failed(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)
    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_FAILED)

    result = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )

    assert result.outcome is VerificationOutcome.FAILED
    assert case.current_state is CaseState.FAILED


def test_no_event_yet_stays_pending_not_recovered_not_failed(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)

    result = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )

    assert result.outcome is VerificationOutcome.STILL_PENDING
    assert result.transition is None
    assert case.current_state is CaseState.VERIFICATION_PENDING


def test_authorized_but_not_captured_stays_pending(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)
    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_AUTHORIZED)

    result = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )

    assert result.outcome is VerificationOutcome.STILL_PENDING
    assert case.current_state is CaseState.VERIFICATION_PENDING


def test_provider_error_never_reaches_recovered(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)
    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_CAPTURED)

    result = run_verification(db_session, BrokenProvider(), case_id=case.id, correlation_id=uuid.uuid4())

    assert result.outcome is VerificationOutcome.ERROR
    assert result.transition is None
    assert case.current_state is CaseState.VERIFICATION_PENDING
    assert result.verification.provider_status is None
    assert "TimeoutError" in result.verification.raw_response["error_type"]


def test_captured_with_amount_mismatch_never_reaches_recovered(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm, amount=Decimal("1000.00"))
    insert_payment_event(
        db_session, case, event_type=EventType.PAYMENT_CAPTURED, amount=Decimal("500.00")
    )

    result = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )

    assert result.outcome is VerificationOutcome.ESCALATED
    assert case.current_state is CaseState.ESCALATED
    assert case.current_state is not CaseState.RECOVERED


def test_unrecognized_provider_status_never_reaches_recovered(db_session):

    class WeirdStatusProvider:
        mode = ProviderMode.SIMULATION_MODE

        def verify_payment(self, payment_id: str) -> VerificationResult:
            return VerificationResult(
                mode=self.mode, payment_id=payment_id, status="pending_manual_review",
                amount=None, currency=None, raw_response={}, fetched_at=datetime.now(timezone.utc),
            )

    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)

    result = run_verification(db_session, WeirdStatusProvider(), case_id=case.id, correlation_id=uuid.uuid4())

    assert result.outcome is VerificationOutcome.ESCALATED
    assert case.current_state is CaseState.ESCALATED


def test_cannot_verify_a_case_not_in_verification_pending(db_session):
    sm = RecoveryStateMachine(db_session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_1",
        amount=Decimal("100.00"), reason="r", actor="a",
    )

    with pytest.raises(WrongCaseStateError):
        run_verification(
            db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
        )


def test_cannot_reverify_an_already_recovered_case_into_a_second_transition(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)
    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_CAPTURED)
    run_verification(db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4())
    assert case.current_state is CaseState.RECOVERED

    with pytest.raises(WrongCaseStateError):
        run_verification(
            db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
        )


def test_every_verification_attempt_is_persisted_even_when_inconclusive(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)

    run_verification(db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4())
    run_verification(db_session, BrokenProvider(), case_id=case.id, correlation_id=uuid.uuid4())

    rows = db_session.query(PaymentVerification).filter_by(case_id=case.id).all()
    assert len(rows) == 2
    assert {r.outcome for r in rows} == {VerificationOutcome.STILL_PENDING, VerificationOutcome.ERROR}
    assert case.current_state is CaseState.VERIFICATION_PENDING


def test_only_verification_module_ever_transitions_a_case_to_recovered():
    import inspect
    import pkgutil

    import services

    offending_modules = []
    for module_info in pkgutil.walk_packages(services.__path__, prefix="services."):
        if module_info.name == "services.payments.verification":
            continue
        try:
            module = __import__(module_info.name, fromlist=["_"])
        except Exception:
            continue
        try:
            source = inspect.getsource(module)
        except (OSError, TypeError):
            continue
        if "CaseState.RECOVERED" in source and "to_state=CaseState.RECOVERED" in source.replace(" ", ""):
            offending_modules.append(module_info.name)

    assert offending_modules == []
