
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.enums import RecoveryAction
from models.recovery_config import RecoveryConfig
from services.recovery.exceptions import RecoveryConfigNotFoundError

DEFAULT_RECOVERY_CONFIG = dict(
    default_probability_by_action={
        RecoveryAction.RETRY.value: 0.20,
        RecoveryAction.SEND_RECOVERY_REMINDER.value: 0.15,
        RecoveryAction.SEND_RECOVERY_LINK.value: 0.15,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD.value: 0.10,
    },
    action_cost_by_action={
        RecoveryAction.RETRY.value: 2.0,
        RecoveryAction.SEND_RECOVERY_REMINDER.value: 0.5,
        RecoveryAction.SEND_RECOVERY_LINK.value: 0.5,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD.value: 1.0,
    },
    risk_cost_multiplier=0.05,
    min_sample_size=30,
    smoothing_alpha=1.0,
    smoothing_beta=1.0,
)


def _to_snapshot(row: RecoveryConfig):
    from services.recovery.expected_value import RecoveryConfigSnapshot

    return RecoveryConfigSnapshot(
        id=row.id,
        version=row.version,
        merchant_id=row.merchant_id,
        default_probability_by_action={
            RecoveryAction(k): v for k, v in row.default_probability_by_action.items()
        },
        action_cost_by_action={
            RecoveryAction(k): Decimal(str(v)) for k, v in row.action_cost_by_action.items()
        },
        risk_cost_multiplier=row.risk_cost_multiplier,
        min_sample_size=row.min_sample_size,
        smoothing_alpha=row.smoothing_alpha,
        smoothing_beta=row.smoothing_beta,
    )


def get_active_recovery_config(session: Session, merchant_id: str | None):
    row = None
    if merchant_id is not None:
        row = session.execute(
            select(RecoveryConfig).where(
                RecoveryConfig.merchant_id == merchant_id, RecoveryConfig.is_active.is_(True)
            )
        ).scalar_one_or_none()

    if row is None:
        row = session.execute(
            select(RecoveryConfig).where(
                RecoveryConfig.merchant_id.is_(None), RecoveryConfig.is_active.is_(True)
            )
        ).scalar_one_or_none()

    if row is None:
        raise RecoveryConfigNotFoundError(merchant_id)

    return _to_snapshot(row)


def activate_new_recovery_config_version(
    session: Session, *, merchant_id: str | None, created_by: str, **fields
) -> RecoveryConfig:
    current = session.execute(
        select(RecoveryConfig).where(
            RecoveryConfig.merchant_id == merchant_id, RecoveryConfig.is_active.is_(True)
        )
    ).scalar_one_or_none()

    next_version = (current.version + 1) if current else 1
    if current is not None:
        current.is_active = False

    new_row = RecoveryConfig(
        merchant_id=merchant_id, version=next_version, is_active=True, created_by=created_by,
        **fields,
    )
    session.add(new_row)
    session.flush()
    return new_row


def ensure_default_recovery_config(session: Session, *, created_by: str = "system:seed") -> RecoveryConfig:
    existing = session.execute(
        select(RecoveryConfig).where(
            RecoveryConfig.merchant_id.is_(None), RecoveryConfig.is_active.is_(True)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    return activate_new_recovery_config_version(
        session, merchant_id=None, created_by=created_by, **DEFAULT_RECOVERY_CONFIG
    )
