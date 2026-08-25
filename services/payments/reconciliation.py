
import uuid

from sqlalchemy.orm import Session

from models.enums import CaseState
from services.payments.provider import PaymentProvider
from services.payments.verification import VerificationRunResult, run_verification
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.state_machine import RecoveryStateMachine


def reconcile_and_reverify(
    session: Session,
    provider: PaymentProvider,
    *,
    case_id: uuid.UUID,
    correlation_id: uuid.UUID,
    reason: str,
) -> VerificationRunResult:
    sm = RecoveryStateMachine(session)
    case = sm.get_case(case_id)
    if case.current_state is not CaseState.FAILED:
        raise WrongCaseStateError(case_id, CaseState.FAILED, case.current_state)

    sm.transition(
        case_id, to_state=CaseState.VERIFICATION_PENDING, reason=reason,
        actor="system:reconciliation", correlation_id=correlation_id,
    )
    return run_verification(session, provider, case_id=case_id, correlation_id=correlation_id)
