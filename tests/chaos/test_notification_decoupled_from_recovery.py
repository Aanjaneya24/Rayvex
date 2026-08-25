
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from models.enums import CaseState, CaseType, EventType, ProcessingStatus, RecoveryAction
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.payments.provider import ProviderMode, VerificationResult
from services.payments.verification import run_verification
from services.recovery.case_orchestrator import execute_and_verify
from services.recovery.state_machine import RecoveryStateMachine


class StillPendingProvider:

    mode = ProviderMode.SIMULATION_MODE

    def verify_payment(self, payment_id: str) -> VerificationResult:
        return VerificationResult(
            mode=ProviderMode.SIMULATION_MODE, payment_id=payment_id, status="authorized",
            amount=Decimal("1000.00"), currency="INR", raw_response={}, fetched_at=datetime.now(timezone.utc),
        )


def _drive_case_to_action_pending(sm: RecoveryStateMachine) -> uuid.UUID:
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_notif",
        customer_id="cust_1", payment_id="pay_notif_1", order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="otp_failure",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    for to_state in [
        CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION, CaseState.ACTION_PENDING,
    ]:
        sm.transition(case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
                       correlation_id=uuid.uuid4())
    return case.id


def test_a_notification_action_never_produces_recovered_on_its_own(db_session):
    sm = RecoveryStateMachine(db_session)
    case_id = _drive_case_to_action_pending(sm)

    result = execute_and_verify(
        db_session, StillPendingProvider(), case_id=case_id,
        action=RecoveryAction.SEND_RECOVERY_REMINDER, correlation_id=uuid.uuid4(),
    )

    case = sm.get_case(case_id)
    assert case.current_state is CaseState.VERIFICATION_PENDING
    assert case.current_state is not CaseState.RECOVERED
    assert result.outcome.value == "STILL_PENDING"


def test_a_late_capture_event_not_a_notification_is_what_can_still_recover_the_case(db_session):
    sm = RecoveryStateMachine(db_session)
    case_id = _drive_case_to_action_pending(sm)
    execute_and_verify(
        db_session, StillPendingProvider(), case_id=case_id,
        action=RecoveryAction.SEND_RECOVERY_REMINDER, correlation_id=uuid.uuid4(),
    )
    case = sm.get_case(case_id)
    assert case.current_state is CaseState.VERIFICATION_PENDING

    class NowCapturedProvider:
        mode = ProviderMode.SIMULATION_MODE

        def verify_payment(self, payment_id: str) -> VerificationResult:
            return VerificationResult(
                mode=ProviderMode.SIMULATION_MODE, payment_id=payment_id, status="captured",
                amount=Decimal("1000.00"), currency="INR", raw_response={},
                fetched_at=datetime.now(timezone.utc),
            )

    result = run_verification(
        db_session, NowCapturedProvider(), case_id=case_id, correlation_id=uuid.uuid4(),
    )

    case = sm.get_case(case_id)
    assert case.current_state is CaseState.RECOVERED
    assert result.outcome.value == "RECOVERED"
