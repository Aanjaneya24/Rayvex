
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth import AuthenticatedUser, get_current_user, require_reviewer
from apps.api.deps import get_db, get_redis
from models.agent_decision import AgentDecision
from models.case import Case
from models.enums import CaseState, HumanReviewDecision, RecoveryAction
from models.human_review_action import HumanReviewAction
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.human_review import InvalidHumanReviewError, review_escalated_case
from services.recovery.state_machine import RecoveryStateMachine

router = APIRouter(prefix="/escalations", tags=["escalations"])


class ReviewRequest(BaseModel):
    decision: HumanReviewDecision
    reason: str = Field(min_length=1)
    action: RecoveryAction | None = None


@router.get("")
def list_escalations(
    db: Session = Depends(get_db),
    _user: AuthenticatedUser = Depends(get_current_user),
):
    cases = (
        db.query(Case)
        .filter(Case.current_state == CaseState.ESCALATED)
        .order_by(Case.updated_at.desc())
        .all()
    )
    latest_decisions = {
        d.case_id: d
        for d in db.query(AgentDecision)
        .filter(AgentDecision.case_id.in_([c.id for c in cases]))
        .order_by(AgentDecision.created_at.asc())
        .all()
    }
    return {
        "total": len(cases),
        "escalations": [
            {
                "case_id": str(c.id),
                "merchant_id": c.merchant_id,
                "amount": str(c.amount),
                "currency": c.currency,
                "failure_code": c.failure_code,
                "proposed_action": latest_decisions[c.id].proposed_action.value if c.id in latest_decisions else None,
                "confidence": latest_decisions[c.id].confidence if c.id in latest_decisions else None,
                "escalated_at": c.updated_at.isoformat(),
            }
            for c in cases
        ],
    }


@router.get("/{case_id}")
def get_escalation_detail(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: AuthenticatedUser = Depends(get_current_user),
):
    sm = RecoveryStateMachine(db)
    try:
        case = sm.get_case(case_id)
    except Exception:
        raise HTTPException(status_code=404, detail="case not found")
    if case.current_state is not CaseState.ESCALATED:
        raise HTTPException(status_code=409, detail=f"case is {case.current_state.value}, not ESCALATED")

    history = sm.history(case_id)
    agent_decisions = (
        db.query(AgentDecision).filter_by(case_id=case_id).order_by(AgentDecision.created_at).all()
    )
    prior_reviews = (
        db.query(HumanReviewAction).filter_by(case_id=case_id).order_by(HumanReviewAction.created_at).all()
    )
    return {
        "case_id": str(case.id),
        "merchant_id": case.merchant_id,
        "amount": str(case.amount),
        "currency": case.currency,
        "failure_code": case.failure_code,
        "payment_method": case.payment_method,
        "timeline": [
            {
                "from_state": t.from_state.value if t.from_state else None,
                "to_state": t.to_state.value, "reason": t.reason, "actor": t.actor,
                "evidence": t.evidence, "created_at": t.created_at.isoformat(),
            }
            for t in history
        ],
        "agent_trace": [
            {
                "proposed_action": d.proposed_action.value, "reason": d.reason,
                "confidence": d.confidence, "risk_level": d.risk_level.value,
                "model_backend": d.model_backend, "created_at": d.created_at.isoformat(),
            }
            for d in agent_decisions
        ],
        "prior_reviews": [
            {
                "reviewer": r.reviewer, "decision": r.decision.value,
                "original_proposed_action": r.original_proposed_action.value if r.original_proposed_action else None,
                "final_action": r.final_action.value if r.final_action else None,
                "reason": r.reason, "created_at": r.created_at.isoformat(),
            }
            for r in prior_reviews
        ],
    }


@router.post("/{case_id}/review")
def review_case(
    case_id: uuid.UUID,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    redis_client=Depends(get_redis),
    user: AuthenticatedUser = Depends(require_reviewer),
):
    try:
        result = review_escalated_case(
            db, redis_client, case_id=case_id, reviewer=user.username,
            decision=body.decision, reason=body.reason, action=body.action,
        )
    except WrongCaseStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidHumanReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "review_id": str(result.review_action.id),
        "decision": result.review_action.decision.value,
        "final_action": result.review_action.final_action.value if result.review_action.final_action else None,
        "gate_approved": result.gate_result.approved if result.gate_result else None,
        "verification_outcome": (
            result.verification_result.outcome.value if result.verification_result else None
        ),
    }
