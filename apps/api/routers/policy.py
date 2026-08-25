
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth import get_current_user
from apps.api.deps import get_db
from services.policy.config_repository import activate_new_version, get_active_config

router = APIRouter(prefix="/policy", tags=["policy"], dependencies=[Depends(get_current_user)])


class PolicyConfigUpdate(BaseModel):
    merchant_id: str | None = None
    max_retry_count: int
    cooldown_seconds: int
    max_automated_recovery_amount: float
    max_daily_attempts_per_customer: int
    prohibited_retry_failure_codes: list[str]
    suspicious_velocity_threshold: int
    suspicious_velocity_window_seconds: int
    high_value_threshold: float
    allowed_actions_by_failure_code: dict[str, list[str]]
    allowed_communication_hours_start: int
    allowed_communication_hours_end: int
    max_interventions_per_case: int
    risk_score_threshold: float
    updated_by: str = "merchant_control_center"


def _serialize(snapshot) -> dict:
    return {
        "version": snapshot.version, "merchant_id": snapshot.merchant_id,
        "max_retry_count": snapshot.max_retry_count, "cooldown_seconds": snapshot.cooldown_seconds,
        "max_automated_recovery_amount": str(snapshot.max_automated_recovery_amount),
        "max_daily_attempts_per_customer": snapshot.max_daily_attempts_per_customer,
        "prohibited_retry_failure_codes": sorted(snapshot.prohibited_retry_failure_codes),
        "suspicious_velocity_threshold": snapshot.suspicious_velocity_threshold,
        "suspicious_velocity_window_seconds": snapshot.suspicious_velocity_window_seconds,
        "high_value_threshold": str(snapshot.high_value_threshold),
        "allowed_actions_by_failure_code": {
            k: sorted(a.value for a in v) for k, v in snapshot.allowed_actions_by_failure_code.items()
        },
        "allowed_communication_hours_start": snapshot.allowed_communication_hours_start,
        "allowed_communication_hours_end": snapshot.allowed_communication_hours_end,
        "max_interventions_per_case": snapshot.max_interventions_per_case,
        "risk_score_threshold": snapshot.risk_score_threshold,
    }


@router.get("/config")
def get_policy_config(merchant_id: str | None = None, db: Session = Depends(get_db)):
    snapshot = get_active_config(db, merchant_id)
    return _serialize(snapshot)


@router.put("/config")
def update_policy_config(body: PolicyConfigUpdate, db: Session = Depends(get_db)):
    fields = body.model_dump(exclude={"merchant_id", "updated_by"})
    activate_new_version(
        db, merchant_id=body.merchant_id, created_by=body.updated_by, **fields,
    )
    snapshot = get_active_config(db, body.merchant_id)
    return _serialize(snapshot)
