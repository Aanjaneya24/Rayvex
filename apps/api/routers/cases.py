
import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import cast, or_, String
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.deps import get_db, get_redis
from models.agent_decision import AgentDecision
from models.case import Case
from models.payment_verification import PaymentVerification
from models.policy_decision import PolicyDecision
from services.agent.tools.reasoning_tools import CANDIDATE_INTERVENTIONAL_ACTIONS
from services.policy.config_repository import get_active_config
from services.recovery.expected_value import evaluate_candidate_actions
from services.recovery.probability import RecoveryCaseContext
from services.recovery.probability_factory import build_probability_estimator
from services.recovery.recovery_config_repository import get_active_recovery_config
from services.recovery.state_machine import RecoveryStateMachine
from services.risk.risk_scoring import check_risk as compute_risk_assessment

router = APIRouter(prefix="/cases", tags=["cases"], dependencies=[Depends(get_current_user)])


def _case_summary(case: Case, latest_decision: AgentDecision | None) -> dict:
    return {
        "case_id": str(case.id),
        "merchant_id": case.merchant_id,
        "amount": str(case.amount),
        "currency": case.currency,
        "failure_code": case.failure_code,
        "case_type": case.case_type.value,
        "status": case.current_state.value,
        "recovery_confidence": latest_decision.confidence if latest_decision else None,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


@router.get("/failure-codes")
def list_failure_codes(db: Session = Depends(get_db)):
    rows = (
        db.query(Case.failure_code)
        .filter(Case.failure_code.isnot(None))
        .distinct()
        .order_by(Case.failure_code)
        .all()
    )
    return {"failure_codes": [r[0] for r in rows]}


@router.get("")
def list_cases(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Free-text search across case ID, payment ID, order ID, customer ID, and merchant ID"),
    status: str | None = Query(default=None),
    failure_code: str | None = Query(default=None),
    amount_min: Decimal | None = Query(default=None),
    amount_max: Decimal | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = db.query(Case)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                cast(Case.id, String).ilike(pattern),
                Case.payment_id.ilike(pattern),
                Case.order_id.ilike(pattern),
                Case.customer_id.ilike(pattern),
                Case.merchant_id.ilike(pattern),
            )
        )
    if status:
        query = query.filter(Case.current_state == status)
    if failure_code:
        query = query.filter(Case.failure_code == failure_code)
    if amount_min is not None:
        query = query.filter(Case.amount >= amount_min)
    if amount_max is not None:
        query = query.filter(Case.amount <= amount_max)
    if created_from is not None:
        query = query.filter(Case.created_at >= created_from)
    if created_to is not None:
        query = query.filter(Case.created_at <= created_to)
    total = query.count()
    cases = query.order_by(Case.updated_at.desc()).offset(offset).limit(limit).all()

    latest_decisions = {
        d.case_id: d
        for d in db.query(AgentDecision)
        .filter(AgentDecision.case_id.in_([c.id for c in cases]))
        .order_by(AgentDecision.created_at.asc())
        .all()
    }
    return {
        "total": total, "limit": limit, "offset": offset,
        "cases": [_case_summary(c, latest_decisions.get(c.id)) for c in cases],
    }


def _alternatives_considered(db: Session, redis_client, case: Case, chosen_action) -> list[dict]:
    if not case.failure_code or not case.payment_method:
        return []
    config = get_active_recovery_config(db, case.merchant_id)
    policy_config = get_active_config(db, case.merchant_id)
    estimator = build_probability_estimator()
    context = RecoveryCaseContext(
        merchant_id=case.merchant_id, failure_code=case.failure_code,
        payment_method=case.payment_method, amount=case.amount,
    )
    risk = compute_risk_assessment(
        db, redis_client, case_id=case.id, customer_id=case.customer_id or "",
        velocity_window_seconds=policy_config.suspicious_velocity_window_seconds,
        velocity_threshold=policy_config.suspicious_velocity_threshold,
    )
    evaluations = evaluate_candidate_actions(
        db, estimator, context=context, candidate_actions=CANDIDATE_INTERVENTIONAL_ACTIONS,
        risk_score=risk.risk_score, config=config,
    )
    return [
        {
            "action": e.action.value,
            "probability": e.probability_estimate.probability,
            "source_tier": e.probability_estimate.source_tier,
            "expected_recovery_value": float(e.expected_recovery_value),
            "action_cost": float(e.action_cost),
            "chosen": chosen_action is not None and e.action == chosen_action,
        }
        for e in evaluations
    ]


@router.get("/{case_id}")
def get_case_detail(case_id: uuid.UUID, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    sm = RecoveryStateMachine(db)
    try:
        case = sm.get_case(case_id)
    except Exception:
        raise HTTPException(status_code=404, detail="case not found")

    history = sm.history(case_id)
    policy_decisions = (
        db.query(PolicyDecision).filter_by(case_id=case_id).order_by(PolicyDecision.created_at).all()
    )
    agent_decisions = (
        db.query(AgentDecision).filter_by(case_id=case_id).order_by(AgentDecision.created_at).all()
    )
    verifications = (
        db.query(PaymentVerification).filter_by(case_id=case_id).order_by(PaymentVerification.created_at).all()
    )
    latest_decision = agent_decisions[-1] if agent_decisions else None
    try:
        alternatives_considered = _alternatives_considered(
            db, redis_client, case, latest_decision.proposed_action if latest_decision else None,
        )
    except Exception:
        alternatives_considered = []

    return {
        "case": _case_summary(case, latest_decision),
        "alternatives_considered": alternatives_considered,
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
                "proposed_action": d.proposed_action.value, "reason": d.reason, "confidence": d.confidence,
                "expected_recovery_value": d.expected_recovery_value, "risk_level": d.risk_level.value,
                "model_backend": d.model_backend, "model_name": d.model_name,
                "prompt_version": d.prompt_version, "schema_version": d.schema_version,
                "tool_trace": d.tool_trace, "created_at": d.created_at.isoformat(),
                "llm_call_count": d.llm_call_count, "total_latency_ms": d.total_latency_ms,
                "estimated_cost_usd": d.estimated_cost_usd,
            }
            for d in agent_decisions
        ],
        "policy_checks": [
            {
                "proposed_action": p.proposed_action.value, "verdict_type": p.verdict_type.value,
                "resulting_action": p.resulting_action.value if p.resulting_action else None,
                "rule_id": p.rule_id, "reason": p.reason, "requires_escalation": p.requires_escalation,
                "policy_config_version": p.policy_config_version, "context_snapshot": p.context_snapshot,
                "created_at": p.created_at.isoformat(),
            }
            for p in policy_decisions
        ],
        "verification_proof": [
            {
                "mode": v.mode.value, "provider_status": v.provider_status, "outcome": v.outcome.value,
                "raw_response": v.raw_response, "created_at": v.created_at.isoformat(),
            }
            for v in verifications
        ],
    }
