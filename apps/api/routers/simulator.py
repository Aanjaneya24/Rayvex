
import dataclasses
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.deps import get_db
from services.evaluation.benchmark import run_benchmark
from services.policy.config_repository import get_active_config

router = APIRouter(prefix="/simulator", tags=["simulator"], dependencies=[Depends(get_current_user)])

ALLOWED_PREVIEW_CASE_COUNTS = {100, 500, 1000}


class PreviewRequest(BaseModel):
    case_count: int = 500
    seed: int = 42
    max_retry_count: int | None = None
    cooldown_seconds: int | None = None
    max_automated_recovery_amount: Decimal | None = None
    max_daily_attempts_per_customer: int | None = None
    suspicious_velocity_threshold: int | None = None
    high_value_threshold: Decimal | None = None
    risk_score_threshold: float | None = None


def _serialize_preview(run) -> dict:
    return {
        "naive_retry": run.naive_retry_metrics,
        "intelligent_recovery": run.intelligent_recovery_metrics,
        "unnecessary_actions_avoided": run.unnecessary_actions_avoided,
        "incremental_verified_revenue": str(run.incremental_verified_revenue),
    }


@router.post("/preview")
def preview_policy_change(body: PreviewRequest, db: Session = Depends(get_db)):
    if body.case_count not in ALLOWED_PREVIEW_CASE_COUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"case_count must be one of {sorted(ALLOWED_PREVIEW_CASE_COUNTS)}",
        )

    baseline_policy = get_active_config(db, merchant_id=None)
    overrides = {
        field: value
        for field, value in body.model_dump(exclude={"case_count", "seed"}).items()
        if value is not None
    }
    if not overrides:
        raise HTTPException(status_code=400, detail="No threshold overrides supplied; nothing to preview.")
    draft_policy = dataclasses.replace(baseline_policy, **overrides)

    baseline_run = run_benchmark(db, seed=body.seed, n=body.case_count, persist=False)
    draft_run = run_benchmark(
        db, seed=body.seed, n=body.case_count, policy_config_override=draft_policy, persist=False,
    )

    return {
        "case_count": body.case_count,
        "seed": body.seed,
        "changed_fields": sorted(overrides.keys()),
        "current_config_version": baseline_policy.version,
        "baseline": _serialize_preview(baseline_run),
        "draft": _serialize_preview(draft_run),
    }
