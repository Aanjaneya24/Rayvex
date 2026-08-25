
import uuid
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from scipy import stats
from sqlalchemy import case as sql_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.ab_experiment_run import ABExperimentRun
from models.enums import RecoveryAction
from models.merchant_recovery_outcome import MerchantRecoveryOutcome
from models.synthetic_recovery_outcome import SyntheticRecoveryOutcome
from services.recovery.expected_value import RecoveryConfigSnapshot

RESULT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
RESULT_NOT_SIGNIFICANT = "NOT_SIGNIFICANT"
RESULT_WINNER_A = "WINNER_A"
RESULT_WINNER_B = "WINNER_B"

DEFAULT_MIN_SAMPLE_SIZE = 30
DEFAULT_SIGNIFICANCE_LEVEL = 0.05


@dataclass(frozen=True)
class ArmStats:
    sample_size: int
    successes: int
    revenue: Decimal

    @property
    def recovery_rate(self) -> float:
        return (self.successes / self.sample_size) if self.sample_size else 0.0


@dataclass(frozen=True)
class ABExperimentResult:
    ab_experiment_run_id: uuid.UUID
    result: str
    p_value: float | None
    arm_a: ArmStats
    arm_b: ArmStats
    cost_per_recovered_rupee_a: float | None
    cost_per_recovered_rupee_b: float | None


def _population_stats(
    session: Session, *, failure_code: str, payment_method: str, action: RecoveryAction,
) -> ArmStats:
    synthetic_stmt = select(
        func.count().label("total"),
        func.coalesce(func.sum(sql_case((SyntheticRecoveryOutcome.recovered.is_(True), 1), else_=0)), 0).label("successes"),
        func.coalesce(func.sum(sql_case((SyntheticRecoveryOutcome.recovered.is_(True), SyntheticRecoveryOutcome.amount), else_=0)), 0).label("revenue"),
    ).where(
        SyntheticRecoveryOutcome.failure_code == failure_code,
        SyntheticRecoveryOutcome.payment_method == payment_method,
        SyntheticRecoveryOutcome.action_taken == action,
    )
    s_total, s_successes, s_revenue = session.execute(synthetic_stmt).one()

    real_stmt = select(
        func.count().label("total"),
        func.coalesce(func.sum(sql_case((MerchantRecoveryOutcome.recovered.is_(True), 1), else_=0)), 0).label("successes"),
        func.coalesce(func.sum(sql_case((MerchantRecoveryOutcome.recovered.is_(True), MerchantRecoveryOutcome.amount), else_=0)), 0).label("revenue"),
    ).where(
        MerchantRecoveryOutcome.failure_code == failure_code,
        MerchantRecoveryOutcome.payment_method == payment_method,
        MerchantRecoveryOutcome.action_taken == action,
    )
    r_total, r_successes, r_revenue = session.execute(real_stmt).one()

    return ArmStats(
        sample_size=int(s_total) + int(r_total),
        successes=int(s_successes) + int(r_successes),
        revenue=Decimal(s_revenue) + Decimal(r_revenue),
    )


def _two_proportion_z_test(arm_a: ArmStats, arm_b: ArmStats) -> float | None:
    n1, n2 = arm_a.sample_size, arm_b.sample_size
    x1, x2 = arm_a.successes, arm_b.successes
    pooled = (x1 + x2) / (n1 + n2)
    if pooled in (0.0, 1.0):
        return None
    se = (pooled * (1 - pooled) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:
        return None
    p1, p2 = x1 / n1, x2 / n2
    z = (p1 - p2) / se
    return float(2 * (1 - stats.norm.cdf(abs(z))))


def _cost_per_recovered_rupee(
    arm: ArmStats, *, action: RecoveryAction, config: RecoveryConfigSnapshot,
) -> float | None:
    if arm.revenue <= 0:
        return None
    total_cost = config.action_cost_by_action[action] * arm.sample_size
    return float(total_cost / arm.revenue)


def run_ab_experiment(
    session: Session, *, failure_code: str, payment_method: str,
    action_a: RecoveryAction, action_b: RecoveryAction, config: RecoveryConfigSnapshot,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    significance_level: float = DEFAULT_SIGNIFICANCE_LEVEL,
) -> ABExperimentResult:
    arm_a = _population_stats(session, failure_code=failure_code, payment_method=payment_method, action=action_a)
    arm_b = _population_stats(session, failure_code=failure_code, payment_method=payment_method, action=action_b)

    if arm_a.sample_size < min_sample_size or arm_b.sample_size < min_sample_size:
        result = RESULT_INSUFFICIENT_EVIDENCE
        p_value = None
    else:
        p_value = _two_proportion_z_test(arm_a, arm_b)
        if p_value is None or p_value >= significance_level:
            result = RESULT_NOT_SIGNIFICANT
        elif arm_a.recovery_rate > arm_b.recovery_rate:
            result = RESULT_WINNER_A
        else:
            result = RESULT_WINNER_B

    cost_a = _cost_per_recovered_rupee(arm_a, action=action_a, config=config)
    cost_b = _cost_per_recovered_rupee(arm_b, action=action_b, config=config)

    run_id = uuid.uuid4()
    row = ABExperimentRun(
        id=run_id, failure_code=failure_code, payment_method=payment_method,
        action_a=action_a, action_b=action_b,
        sample_size_a=arm_a.sample_size, sample_size_b=arm_b.sample_size,
        successes_a=arm_a.successes, successes_b=arm_b.successes,
        recovery_rate_a=arm_a.recovery_rate, recovery_rate_b=arm_b.recovery_rate,
        revenue_a=arm_a.revenue, revenue_b=arm_b.revenue,
        cost_per_recovered_rupee_a=cost_a, cost_per_recovered_rupee_b=cost_b,
        p_value=p_value, min_sample_size=min_sample_size,
        significance_level=significance_level, result=result,
    )
    session.add(row)
    session.flush()

    return ABExperimentResult(
        ab_experiment_run_id=run_id, result=result, p_value=p_value,
        arm_a=arm_a, arm_b=arm_b,
        cost_per_recovered_rupee_a=cost_a, cost_per_recovered_rupee_b=cost_b,
    )
