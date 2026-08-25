
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.enums import RecoveryAction
from models.policy_config import PolicyConfig
from services.policy.context import PolicyConfigSnapshot
from services.policy.exceptions import PolicyConfigNotFoundError

DEFAULT_GLOBAL_CONFIG = dict(
    max_retry_count=3,
    cooldown_seconds=300,
    max_automated_recovery_amount=Decimal("50000.00"),
    max_daily_attempts_per_customer=5,
    prohibited_retry_failure_codes=["insufficient_funds"],
    suspicious_velocity_threshold=5,
    suspicious_velocity_window_seconds=600,
    high_value_threshold=Decimal("20000.00"),
    allowed_actions_by_failure_code={},
    allowed_communication_hours_start=8,
    allowed_communication_hours_end=21,
    max_interventions_per_case=5,
    risk_score_threshold=0.7,
)


def _to_snapshot(row: PolicyConfig) -> PolicyConfigSnapshot:
    return PolicyConfigSnapshot(
        id=row.id,
        version=row.version,
        merchant_id=row.merchant_id,
        max_retry_count=row.max_retry_count,
        cooldown_seconds=row.cooldown_seconds,
        max_automated_recovery_amount=row.max_automated_recovery_amount,
        max_daily_attempts_per_customer=row.max_daily_attempts_per_customer,
        prohibited_retry_failure_codes=frozenset(row.prohibited_retry_failure_codes),
        suspicious_velocity_threshold=row.suspicious_velocity_threshold,
        suspicious_velocity_window_seconds=row.suspicious_velocity_window_seconds,
        high_value_threshold=row.high_value_threshold,
        allowed_actions_by_failure_code={
            failure_code: frozenset(RecoveryAction(a) for a in actions)
            for failure_code, actions in row.allowed_actions_by_failure_code.items()
        },
        allowed_communication_hours_start=row.allowed_communication_hours_start,
        allowed_communication_hours_end=row.allowed_communication_hours_end,
        max_interventions_per_case=row.max_interventions_per_case,
        risk_score_threshold=row.risk_score_threshold,
    )


def get_active_config(session: Session, merchant_id: str | None) -> PolicyConfigSnapshot:
    row = None
    if merchant_id is not None:
        row = session.execute(
            select(PolicyConfig).where(
                PolicyConfig.merchant_id == merchant_id, PolicyConfig.is_active.is_(True)
            )
        ).scalar_one_or_none()

    if row is None:
        row = session.execute(
            select(PolicyConfig).where(
                PolicyConfig.merchant_id.is_(None), PolicyConfig.is_active.is_(True)
            )
        ).scalar_one_or_none()

    if row is None:
        raise PolicyConfigNotFoundError(merchant_id)

    return _to_snapshot(row)


def activate_new_version(
    session: Session,
    *,
    merchant_id: str | None,
    created_by: str,
    **threshold_fields,
) -> PolicyConfig:
    current = session.execute(
        select(PolicyConfig).where(
            PolicyConfig.merchant_id == merchant_id, PolicyConfig.is_active.is_(True)
        )
    ).scalar_one_or_none()

    next_version = (current.version + 1) if current else 1
    if current is not None:
        current.is_active = False

    new_row = PolicyConfig(
        merchant_id=merchant_id,
        version=next_version,
        is_active=True,
        created_by=created_by,
        **threshold_fields,
    )
    session.add(new_row)
    session.flush()
    return new_row


def ensure_default_global_config(
    session: Session, *, created_by: str = "system:seed"
) -> PolicyConfig:
    existing = session.execute(
        select(PolicyConfig).where(
            PolicyConfig.merchant_id.is_(None), PolicyConfig.is_active.is_(True)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    return activate_new_version(
        session, merchant_id=None, created_by=created_by, **DEFAULT_GLOBAL_CONFIG
    )
