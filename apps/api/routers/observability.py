
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.deps import get_db
from models.agent_decision import AgentDecision
from services.recovery.case_orchestrator import DETERMINISTIC_SKIP_MODEL_BACKEND

router = APIRouter(prefix="/observability", tags=["observability"], dependencies=[Depends(get_current_user)])


@router.get("/summary")
def get_observability_summary(db: Session = Depends(get_db)):
    total_decisions = db.execute(select(func.count()).select_from(AgentDecision)).scalar_one()

    skipped_count = db.execute(
        select(func.count()).where(AgentDecision.model_backend == DETERMINISTIC_SKIP_MODEL_BACKEND)
    ).scalar_one()

    totals = db.execute(
        select(
            func.coalesce(func.sum(AgentDecision.llm_call_count), 0),
            func.coalesce(func.sum(AgentDecision.total_latency_ms), 0),
            func.coalesce(func.sum(AgentDecision.estimated_cost_usd), 0.0),
        )
    ).one()
    total_llm_calls, total_latency_ms, total_estimated_cost_usd = totals

    live_decisions = total_decisions - skipped_count
    avg_latency_ms = (total_latency_ms / live_decisions) if live_decisions else None
    avg_llm_calls = (total_llm_calls / live_decisions) if live_decisions else None

    return {
        "total_decisions": total_decisions,
        "deterministic_skips": skipped_count,
        "deterministic_skip_rate": (skipped_count / total_decisions) if total_decisions else 0.0,
        "total_llm_calls": int(total_llm_calls),
        "total_latency_ms": int(total_latency_ms),
        "total_estimated_cost_usd": float(total_estimated_cost_usd),
        "average_latency_ms_per_live_decision": avg_latency_ms,
        "average_llm_calls_per_live_decision": avg_llm_calls,
    }


@router.get("/cases/{case_id}/trace")
def get_case_trace(case_id, db: Session = Depends(get_db)):
    decisions = (
        db.query(AgentDecision).filter_by(case_id=case_id).order_by(AgentDecision.created_at).all()
    )
    return {
        "case_id": str(case_id),
        "decisions": [
            {
                "agent_decision_id": str(d.id),
                "proposed_action": d.proposed_action.value,
                "model_backend": d.model_backend,
                "model_name": d.model_name,
                "llm_call_count": d.llm_call_count,
                "total_latency_ms": d.total_latency_ms,
                "estimated_cost_usd": d.estimated_cost_usd,
                "tool_trace": d.tool_trace,
                "created_at": d.created_at.isoformat(),
            }
            for d in decisions
        ],
    }
