
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from models.enums import RecoveryAction
from services.evaluation.outcomes_repository import (
    SegmentStats,
    global_baseline_stats,
    merchant_specific_stats,
    real_merchant_specific_stats,
    segment_stats,
)


@dataclass(frozen=True)
class RecoveryCaseContext:
    merchant_id: str
    failure_code: str
    payment_method: str
    amount: Decimal


@dataclass(frozen=True)
class ProbabilityEstimate:
    probability: float
    source_tier: str
    sample_size: int
    real_sample_size: int = 0


def _smooth(stats: SegmentStats, *, alpha: float, beta: float) -> float:
    return (stats.successes + alpha) / (stats.total + alpha + beta)


class RecoveryProbabilityEstimator(Protocol):
    def estimate(
        self, session: Session, *, context: RecoveryCaseContext, action: RecoveryAction, config,
    ) -> ProbabilityEstimate: ...


class EmpiricalRecoveryProbabilityEstimator:

    def estimate(
        self, session: Session, *, context: RecoveryCaseContext, action: RecoveryAction, config,
    ) -> ProbabilityEstimate:
        real_tier1 = real_merchant_specific_stats(
            session, merchant_id=context.merchant_id, failure_code=context.failure_code,
            payment_method=context.payment_method, amount=context.amount, action=action,
        )
        synthetic_tier1 = merchant_specific_stats(
            session, merchant_id=context.merchant_id, failure_code=context.failure_code,
            payment_method=context.payment_method, amount=context.amount, action=action,
        )
        tier1 = SegmentStats(
            successes=real_tier1.successes + synthetic_tier1.successes,
            total=real_tier1.total + synthetic_tier1.total,
        )
        if tier1.total >= config.min_sample_size:
            return ProbabilityEstimate(
                probability=_smooth(tier1, alpha=config.smoothing_alpha, beta=config.smoothing_beta),
                source_tier="merchant_specific", sample_size=tier1.total,
                real_sample_size=real_tier1.total,
            )

        tier2 = segment_stats(
            session, failure_code=context.failure_code, payment_method=context.payment_method,
            amount=context.amount, action=action,
        )
        if tier2.total >= config.min_sample_size:
            return ProbabilityEstimate(
                probability=_smooth(tier2, alpha=config.smoothing_alpha, beta=config.smoothing_beta),
                source_tier="segment", sample_size=tier2.total,
            )

        tier3 = global_baseline_stats(session, failure_code=context.failure_code, action=action)
        if tier3.total >= config.min_sample_size:
            return ProbabilityEstimate(
                probability=_smooth(tier3, alpha=config.smoothing_alpha, beta=config.smoothing_beta),
                source_tier="global_baseline", sample_size=tier3.total,
            )

        return ProbabilityEstimate(
            probability=config.default_probability_by_action[action],
            source_tier="deterministic_default", sample_size=0,
        )
