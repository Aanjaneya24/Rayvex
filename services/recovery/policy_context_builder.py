
from datetime import datetime, timezone

import redis
from sqlalchemy.orm import Session

from models.case import Case
from models.enums import RecoveryAction
from services.policy.context import PolicyConfigSnapshot, PolicyContext
from services.policy.redis_guards import (
    compute_suspicious_velocity,
    get_daily_attempts_count,
    is_cooldown_satisfied,
)
from services.recovery.attempt_counts import count_retry_and_intervention_attempts


def build_policy_context(
    session: Session,
    redis_client: redis.Redis,
    case: Case,
    proposed_action: RecoveryAction,
    config: PolicyConfigSnapshot,
    *,
    risk_score: float,
    current_hour: int | None = None,
) -> PolicyContext:
    retry_count, intervention_count = count_retry_and_intervention_attempts(session, case.id)
    customer_id = case.customer_id or ""

    return PolicyContext(
        failure_code=case.failure_code or "",
        proposed_action=proposed_action,
        amount=case.amount,
        retry_count=retry_count,
        intervention_count=intervention_count,
        daily_attempts_count=get_daily_attempts_count(redis_client, customer_id),
        risk_score=risk_score,
        cooldown_satisfied=is_cooldown_satisfied(redis_client, case.id),
        suspicious_velocity=compute_suspicious_velocity(
            redis_client,
            customer_id=customer_id,
            window_seconds=config.suspicious_velocity_window_seconds,
            threshold=config.suspicious_velocity_threshold,
        ),
        current_hour=(
            current_hour if current_hour is not None else datetime.now(timezone.utc).hour
        ),
    )
