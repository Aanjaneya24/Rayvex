
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from models.case import Case
from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, VerificationOutcome
from models.payment_verification import PaymentVerification
from services.payments.provider import PaymentProvider, VerificationResult
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.merchant_outcomes import record_merchant_outcome
from services.recovery.state_machine import RecoveryStateMachine

_SUCCESSFUL_STATUSES = {"captured"}
_FAILED_STATUSES = {"failed", "refunded"}
_PENDING_STATUSES = {"created", "authorized"}

AMOUNT_MISMATCH_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class VerificationRunResult:
    outcome: VerificationOutcome
    verification: PaymentVerification
    transition: CaseStateTransition | None


def run_verification(
    session: Session,
    provider: PaymentProvider,
    *,
    case_id: uuid.UUID,
    correlation_id: uuid.UUID,
) -> VerificationRunResult:
    sm = RecoveryStateMachine(session)
    case = sm.get_case(case_id)
    if case.current_state is not CaseState.VERIFICATION_PENDING:
        raise WrongCaseStateError(case_id, CaseState.VERIFICATION_PENDING, case.current_state)

    if not case.payment_id:
        raise ValueError(f"case {case_id} has no payment_id to verify against")

    try:
        result = provider.verify_payment(case.payment_id)
    except Exception as exc:
        return _record_error(session, case, exc, mode=provider.mode, correlation_id=correlation_id)

    outcome, to_state = _classify(result, case)

    verification_row = PaymentVerification(
        case_id=case.id, correlation_id=correlation_id, payment_id=case.payment_id,
        mode=result.mode, provider_status=result.status, outcome=outcome,
        raw_response=result.raw_response,
    )
    session.add(verification_row)
    session.flush()

    if outcome is VerificationOutcome.STILL_PENDING:
        return VerificationRunResult(outcome=outcome, verification=verification_row, transition=None)

    transition = sm.transition(
        case.id, to_state=to_state, reason=_reason_for(outcome, result),
        actor="system:verification", correlation_id=correlation_id,
        evidence={
            "mode": result.mode.value, "provider_status": result.status,
            "payment_verification_id": str(verification_row.id),
        },
    )
    verification_row.resulting_transition_id = transition.id
    session.flush()

    if outcome in (VerificationOutcome.RECOVERED, VerificationOutcome.FAILED):
        record_merchant_outcome(session, case, recovered=(outcome is VerificationOutcome.RECOVERED))

    return VerificationRunResult(outcome=outcome, verification=verification_row, transition=transition)


def _record_error(
    session: Session, case: Case, exc: Exception, *, mode, correlation_id: uuid.UUID,
) -> VerificationRunResult:
    verification_row = PaymentVerification(
        case_id=case.id, correlation_id=correlation_id, payment_id=case.payment_id or "",
        mode=mode, provider_status=None, outcome=VerificationOutcome.ERROR,
        raw_response={"error": str(exc), "error_type": type(exc).__name__},
    )
    session.add(verification_row)
    session.flush()
    return VerificationRunResult(outcome=VerificationOutcome.ERROR, verification=verification_row, transition=None)


def _classify(result: VerificationResult, case: Case) -> tuple[VerificationOutcome, CaseState | None]:
    status = result.status

    if status in _SUCCESSFUL_STATUSES:
        if result.amount is not None and abs(result.amount - case.amount) > AMOUNT_MISMATCH_TOLERANCE:
            return VerificationOutcome.ESCALATED, CaseState.ESCALATED
        return VerificationOutcome.RECOVERED, CaseState.RECOVERED

    if status in _FAILED_STATUSES:
        return VerificationOutcome.FAILED, CaseState.FAILED

    if status in _PENDING_STATUSES:
        return VerificationOutcome.STILL_PENDING, None

    return VerificationOutcome.ESCALATED, CaseState.ESCALATED


def _reason_for(outcome: VerificationOutcome, result: VerificationResult) -> str:
    if outcome is VerificationOutcome.RECOVERED:
        return f"Verified successful payment state (status={result.status!r}) via {result.mode.value}"
    if outcome is VerificationOutcome.FAILED:
        return f"Verified unsuccessful payment state (status={result.status!r}) via {result.mode.value}"
    return f"Ambiguous or unexpected payment status ({result.status!r}) via {result.mode.value} — escalating"
