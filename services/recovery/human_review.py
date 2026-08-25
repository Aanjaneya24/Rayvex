
import uuid
from dataclasses import dataclass

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.agent_decision import AgentDecision
from models.enums import CaseState, HumanReviewDecision, RecoveryAction
from models.human_review_action import HumanReviewAction
from services.payments.provider import PaymentProvider
from services.payments.provider_factory import build_default_payment_provider
from services.payments.verification import VerificationRunResult
from services.recovery.action_gate import ActionGateResult, check_action_before_execution
from services.recovery.case_orchestrator import execute_and_verify
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.state_machine import RecoveryStateMachine


class InvalidHumanReviewError(ValueError):
    pass


@dataclass(frozen=True)
class HumanReviewResult:
    review_action: HumanReviewAction
    gate_result: ActionGateResult | None
    verification_result: VerificationRunResult | None


def _latest_proposed_action(session: Session, case_id: uuid.UUID) -> RecoveryAction | None:
    stmt = (
        select(AgentDecision)
        .where(AgentDecision.case_id == case_id)
        .order_by(AgentDecision.created_at.desc())
        .limit(1)
    )
    decision = session.execute(stmt).scalars().first()
    return decision.proposed_action if decision else None


def review_escalated_case(
    session: Session,
    redis_client: redis.Redis,
    *,
    case_id: uuid.UUID,
    reviewer: str,
    decision: HumanReviewDecision,
    reason: str,
    action: RecoveryAction | None = None,
    risk_score: float = 0.1,
    provider: PaymentProvider | None = None,
    correlation_id: uuid.UUID | None = None,
    current_hour: int | None = None,
) -> HumanReviewResult:
    sm = RecoveryStateMachine(session)
    case = sm.get_case(case_id)
    if case.current_state is not CaseState.ESCALATED:
        raise WrongCaseStateError(case_id, CaseState.ESCALATED, case.current_state)

    correlation_id = correlation_id if correlation_id is not None else uuid.uuid4()
    original_proposed_action = _latest_proposed_action(session, case_id)

    if decision is HumanReviewDecision.REJECT:
        final_action = None
        transition = sm.transition(
            case.id, to_state=CaseState.STOPPED, reason=reason,
            actor=f"human:{reviewer}", correlation_id=correlation_id,
            evidence={
                "human_review": True, "decision": decision.value, "reviewer": reviewer,
                "original_proposed_action": original_proposed_action.value if original_proposed_action else None,
            },
        )
        review_row = HumanReviewAction(
            case_id=case.id, correlation_id=correlation_id, reviewer=reviewer,
            decision=decision, original_proposed_action=original_proposed_action,
            final_action=final_action, reason=reason, resulting_transition_id=transition.id,
        )
        session.add(review_row)
        session.flush()
        return HumanReviewResult(review_action=review_row, gate_result=None, verification_result=None)

    if decision is HumanReviewDecision.APPROVE:
        if original_proposed_action is None and action is None:
            raise InvalidHumanReviewError(
                "APPROVE requires an action: this case has no prior proposed action to approve."
            )
        final_action = action if action is not None else original_proposed_action
        if action is not None and original_proposed_action is not None and action != original_proposed_action:
            raise InvalidHumanReviewError(
                f"APPROVE action ({action.value}) does not match the originally proposed "
                f"action ({original_proposed_action.value}) — use OVERRIDE to authorize a "
                f"different action."
            )
    elif decision is HumanReviewDecision.OVERRIDE:
        if action is None:
            raise InvalidHumanReviewError("OVERRIDE requires an explicit action to authorize.")
        final_action = action
    else:
        raise InvalidHumanReviewError(f"Unknown HumanReviewDecision: {decision!r}")

    resume_transition = sm.transition(
        case.id, to_state=CaseState.ACTION_PENDING, reason=reason,
        actor=f"human:{reviewer}", correlation_id=correlation_id,
        evidence={
            "human_review": True, "decision": decision.value, "reviewer": reviewer,
            "original_proposed_action": original_proposed_action.value if original_proposed_action else None,
            "final_action": final_action.value,
        },
    )
    review_row = HumanReviewAction(
        case_id=case.id, correlation_id=correlation_id, reviewer=reviewer,
        decision=decision, original_proposed_action=original_proposed_action,
        final_action=final_action, reason=reason, resulting_transition_id=resume_transition.id,
    )
    session.add(review_row)
    session.flush()

    gate_result = check_action_before_execution(
        session, redis_client, case_id=case.id, proposed_action=final_action,
        correlation_id=correlation_id, risk_score=risk_score, current_hour=current_hour,
    )
    if not gate_result.approved:
        return HumanReviewResult(review_action=review_row, gate_result=gate_result, verification_result=None)

    resolved_provider = provider if provider is not None else build_default_payment_provider(session)
    verification_result = execute_and_verify(
        session, resolved_provider, case_id=case.id, action=final_action, correlation_id=correlation_id,
    )
    return HumanReviewResult(review_action=review_row, gate_result=gate_result, verification_result=verification_result)
