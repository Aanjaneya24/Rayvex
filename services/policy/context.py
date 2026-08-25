
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from models.enums import PolicyVerdictType, RecoveryAction


@dataclass(frozen=True)
class PolicyContext:

    failure_code: str
    proposed_action: RecoveryAction
    amount: Decimal
    retry_count: int
    intervention_count: int
    daily_attempts_count: int
    risk_score: float
    cooldown_satisfied: bool
    suspicious_velocity: bool
    current_hour: int


@dataclass(frozen=True)
class PolicyConfigSnapshot:

    id: object
    version: int
    merchant_id: str | None

    max_retry_count: int
    cooldown_seconds: int
    max_automated_recovery_amount: Decimal
    max_daily_attempts_per_customer: int
    prohibited_retry_failure_codes: frozenset[str]
    suspicious_velocity_threshold: int
    suspicious_velocity_window_seconds: int
    high_value_threshold: Decimal
    allowed_actions_by_failure_code: Mapping[str, frozenset[RecoveryAction]]
    allowed_communication_hours_start: int
    allowed_communication_hours_end: int
    max_interventions_per_case: int
    risk_score_threshold: float


@dataclass(frozen=True)
class PolicyVerdict:

    verdict_type: PolicyVerdictType
    resulting_action: RecoveryAction | None
    rule_id: str
    reason: str
    requires_escalation: bool = False
