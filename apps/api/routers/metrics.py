
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.deps import get_db
from models.benchmark_run import BenchmarkRun
from models.case import Case
from models.enums import CaseState

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(get_current_user)])

TREND_WINDOW = timedelta(hours=24)


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    total_cases, revenue_at_risk = db.execute(
        select(func.count(), func.coalesce(func.sum(Case.amount), 0))
    ).one()

    recovered_count, recovered_revenue = db.execute(
        select(func.count(), func.coalesce(func.sum(Case.amount), 0)).where(
            Case.current_state == CaseState.RECOVERED
        )
    ).one()

    escalated_count = db.execute(
        select(func.count()).where(Case.current_state == CaseState.ESCALATED)
    ).scalar_one()

    avg_recovery_seconds = db.execute(
        select(func.avg(func.extract("epoch", Case.updated_at - Case.created_at))).where(
            Case.current_state == CaseState.RECOVERED
        )
    ).scalar_one()

    latest_benchmark = db.query(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).first()
    incremental_revenue = (
        str(latest_benchmark.incremental_verified_revenue) if latest_benchmark else None
    )

    recovery_rate = float(recovered_revenue) / float(revenue_at_risk) if revenue_at_risk else 0.0
    escalation_rate = escalated_count / total_cases if total_cases else 0.0

    cutoff = datetime.now(timezone.utc) - TREND_WINDOW
    prior_total, prior_revenue_at_risk = db.execute(
        select(func.count(), func.coalesce(func.sum(Case.amount), 0)).where(Case.created_at <= cutoff)
    ).one()
    prior_recovered_count, prior_recovered_revenue = db.execute(
        select(func.count(), func.coalesce(func.sum(Case.amount), 0)).where(
            Case.current_state == CaseState.RECOVERED, Case.created_at <= cutoff,
        )
    ).one()
    prior_recovery_rate = (
        float(prior_recovered_revenue) / float(prior_revenue_at_risk) if prior_revenue_at_risk else None
    )

    return {
        "revenue_at_risk": str(revenue_at_risk),
        "verified_recovered_revenue": str(recovered_revenue),
        "recovery_rate": recovery_rate,
        "incremental_revenue_vs_baseline": incremental_revenue,
        "cases_processed": total_cases,
        "cases_recovered": recovered_count,
        "escalation_rate": escalation_rate,
        "average_recovery_time_seconds": (
            float(avg_recovery_seconds) if avg_recovery_seconds is not None else None
        ),
        "latest_benchmark_run_id": str(latest_benchmark.id) if latest_benchmark else None,
        "revenue_at_risk_trend_pct": _pct_change(float(revenue_at_risk), float(prior_revenue_at_risk)),
        "verified_recovered_revenue_trend_pct": _pct_change(
            float(recovered_revenue), float(prior_recovered_revenue)
        ),
        "recovery_rate_trend_pct": (
            _pct_change(recovery_rate, prior_recovery_rate) if prior_recovery_rate is not None else None
        ),
    }
