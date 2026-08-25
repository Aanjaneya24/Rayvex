
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.case import Case
from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, CaseType
from services.recovery.exceptions import CaseNotFoundError, InvalidTransitionError
from services.recovery.transitions import is_allowed


class RecoveryStateMachine:
    def __init__(self, session: Session):
        self.session = session

    def create_case(
        self,
        *,
        correlation_id: uuid.UUID,
        case_type: CaseType,
        merchant_id: str,
        amount,
        reason: str,
        actor: str,
        customer_id: str | None = None,
        payment_id: str | None = None,
        order_id: str | None = None,
        currency: str = "INR",
        payment_method: str | None = None,
        failure_code: str | None = None,
        failure_reason: str | None = None,
        evidence: dict[str, Any] | None = None,
        triggering_payment_event_id: uuid.UUID | None = None,
    ) -> Case:
        case = Case(
            correlation_id=correlation_id,
            case_type=case_type,
            merchant_id=merchant_id,
            customer_id=customer_id,
            payment_id=payment_id,
            order_id=order_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            failure_code=failure_code,
            failure_reason=failure_reason,
            current_state=CaseState.RECEIVED,
        )
        self.session.add(case)
        self.session.flush()

        transition = CaseStateTransition(
            case_id=case.id,
            correlation_id=correlation_id,
            from_state=None,
            to_state=CaseState.RECEIVED,
            reason=reason,
            actor=actor,
            evidence=evidence or {},
            triggering_payment_event_id=triggering_payment_event_id,
        )
        self.session.add(transition)
        self.session.flush()
        return case

    def transition(
        self,
        case_id: uuid.UUID,
        *,
        to_state: CaseState,
        reason: str,
        actor: str,
        correlation_id: uuid.UUID,
        evidence: dict[str, Any] | None = None,
        triggering_payment_event_id: uuid.UUID | None = None,
        policy_decision_id: uuid.UUID | None = None,
    ) -> CaseStateTransition:
        case = self.session.get(Case, case_id, with_for_update=True)
        if case is None:
            raise CaseNotFoundError(case_id)

        from_state = case.current_state
        if not is_allowed(from_state, to_state):
            raise InvalidTransitionError(from_state, to_state)

        transition = CaseStateTransition(
            case_id=case.id,
            correlation_id=correlation_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            actor=actor,
            evidence=evidence or {},
            triggering_payment_event_id=triggering_payment_event_id,
            policy_decision_id=policy_decision_id,
        )
        self.session.add(transition)
        case.current_state = to_state
        self.session.flush()
        return transition

    def get_case(self, case_id: uuid.UUID) -> Case:
        case = self.session.get(Case, case_id)
        if case is None:
            raise CaseNotFoundError(case_id)
        return case

    def history(self, case_id: uuid.UUID) -> list[CaseStateTransition]:
        self.get_case(case_id)
        return list(
            self.session.execute(
                select(CaseStateTransition)
                .where(CaseStateTransition.case_id == case_id)
                .order_by(CaseStateTransition.created_at)
            ).scalars().all()
        )
