
from dataclasses import dataclass
from decimal import Decimal

from models.enums import RecoveryAction
from services.recovery.probability import (
    ProbabilityEstimate,
    RecoveryCaseContext,
    RecoveryProbabilityEstimator,
)


@dataclass(frozen=True)
class RecoveryConfigSnapshot:

    id: object
    version: int
    merchant_id: str | None
    default_probability_by_action: dict[RecoveryAction, float]
    action_cost_by_action: dict[RecoveryAction, Decimal]
    risk_cost_multiplier: float
    min_sample_size: int
    smoothing_alpha: float
    smoothing_beta: float


@dataclass(frozen=True)
class ActionEvaluation:
    action: RecoveryAction
    probability_estimate: ProbabilityEstimate
    expected_recovery_value: Decimal
    action_cost: Decimal
    expected_risk_cost: Decimal


def calculate_expected_risk_cost(
    *, risk_score: float, amount: Decimal, risk_cost_multiplier: float
) -> Decimal:
    return Decimal(str(risk_score)) * amount * Decimal(str(risk_cost_multiplier))


def calculate_expected_value(
    *, probability: float, recoverable_amount: Decimal, action_cost: Decimal,
    expected_risk_cost: Decimal,
) -> Decimal:
    gross_expected_recovery = Decimal(str(probability)) * recoverable_amount
    return gross_expected_recovery - action_cost - expected_risk_cost


def evaluate_candidate_actions(
    session,
    estimator: RecoveryProbabilityEstimator,
    *,
    context: RecoveryCaseContext,
    candidate_actions: list[RecoveryAction],
    risk_score: float,
    config: RecoveryConfigSnapshot,
) -> list[ActionEvaluation]:
    expected_risk_cost = calculate_expected_risk_cost(
        risk_score=risk_score, amount=context.amount, risk_cost_multiplier=config.risk_cost_multiplier,
    )

    evaluations = []
    for action in candidate_actions:
        estimate = estimator.estimate(session, context=context, action=action, config=config)
        action_cost = config.action_cost_by_action[action]
        expected_value = calculate_expected_value(
            probability=estimate.probability, recoverable_amount=context.amount,
            action_cost=action_cost, expected_risk_cost=expected_risk_cost,
        )
        evaluations.append(
            ActionEvaluation(
                action=action, probability_estimate=estimate,
                expected_recovery_value=expected_value, action_cost=action_cost,
                expected_risk_cost=expected_risk_cost,
            )
        )

    evaluations.sort(key=lambda e: e.expected_recovery_value, reverse=True)
    return evaluations
