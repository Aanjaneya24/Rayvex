
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, RecoveryAction


def count_retry_and_intervention_attempts(
    session: Session, case_id: uuid.UUID
) -> tuple[int, int]:
    rows = session.execute(
        select(CaseStateTransition.evidence).where(
            CaseStateTransition.case_id == case_id,
            CaseStateTransition.to_state == CaseState.ACTION_EXECUTED,
        )
    ).scalars().all()
    retry_count = sum(1 for evidence in rows if evidence.get("action") == RecoveryAction.RETRY.value)
    return retry_count, len(rows)
