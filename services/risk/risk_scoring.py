
import uuid
from dataclasses import dataclass

import redis
from sqlalchemy.orm import Session

from models.enums import RiskLevel
from services.policy.redis_guards import compute_suspicious_velocity
from services.recovery.attempt_counts import count_retry_and_intervention_attempts


@dataclass(frozen=True)
class RiskAssessment:
    risk_score: float
    risk_level: RiskLevel
    suspicious_velocity: bool
    retry_count: int


def risk_level_for(risk_score: float) -> RiskLevel:
    if risk_score >= 0.7:
        return RiskLevel.HIGH
    if risk_score >= 0.3:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def check_risk(
    session: Session,
    redis_client: redis.Redis,
    *,
    case_id: uuid.UUID,
    customer_id: str,
    velocity_window_seconds: int,
    velocity_threshold: int,
) -> RiskAssessment:
    suspicious_velocity = compute_suspicious_velocity(
        redis_client, customer_id=customer_id, window_seconds=velocity_window_seconds,
        threshold=velocity_threshold,
    )
    retry_count, _ = count_retry_and_intervention_attempts(session, case_id)

    risk_score = 0.0
    if suspicious_velocity:
        risk_score += 0.7
    risk_score += min(retry_count * 0.1, 0.3)
    risk_score = min(risk_score, 1.0)

    return RiskAssessment(
        risk_score=risk_score, risk_level=risk_level_for(risk_score),
        suspicious_velocity=suspicious_velocity, retry_count=retry_count,
    )
