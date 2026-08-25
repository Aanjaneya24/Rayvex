
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.case import Case
from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, RecoveryAction
from models.merchant_recovery_outcome import MerchantRecoveryOutcome


def _find_action_taken(session: Session, case_id: uuid.UUID) -> RecoveryAction | None:
    stmt = (
        select(CaseStateTransition)
        .where(
            CaseStateTransition.case_id == case_id,
            CaseStateTransition.to_state == CaseState.ACTION_EXECUTED,
        )
        .order_by(CaseStateTransition.created_at.desc())
        .limit(1)
    )
    transition = session.execute(stmt).scalars().first()
    if transition is None:
        return None
    action_value = transition.evidence.get("action")
    if action_value is None:
        return None
    return RecoveryAction(action_value)


def record_merchant_outcome(session: Session, case: Case, *, recovered: bool) -> MerchantRecoveryOutcome | None:
    action_taken = _find_action_taken(session, case.id)
    if action_taken is None:
        return None

    row = MerchantRecoveryOutcome(
        case_id=case.id,
        merchant_id=case.merchant_id,
        failure_code=case.failure_code or "unknown",
        payment_method=case.payment_method or "unknown",
        amount=case.amount,
        action_taken=action_taken,
        recovered=recovered,
    )
    session.add(row)
    session.flush()
    return row
