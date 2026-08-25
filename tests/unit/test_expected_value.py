
from decimal import Decimal

from models.enums import RecoveryAction
from services.recovery.expected_value import (
    ActionEvaluation,
    RecoveryConfigSnapshot,
    calculate_expected_risk_cost,
    calculate_expected_value,
    evaluate_candidate_actions,
)
from services.recovery.probability import ProbabilityEstimate, RecoveryCaseContext


def test_expected_value_formula():
    ev = calculate_expected_value(
        probability=0.8, recoverable_amount=Decimal("1000.00"),
        action_cost=Decimal("2.00"), expected_risk_cost=Decimal("5.00"),
    )
    assert ev == Decimal("793.00")


def test_expected_value_can_be_negative():
    ev = calculate_expected_value(
        probability=0.05, recoverable_amount=Decimal("100.00"),
        action_cost=Decimal("2.00"), expected_risk_cost=Decimal("10.00"),
    )
    assert ev == Decimal("-7.00")


def test_expected_risk_cost_formula():
    cost = calculate_expected_risk_cost(
        risk_score=0.4, amount=Decimal("1000.00"), risk_cost_multiplier=0.05
    )
    assert cost == Decimal("20.000")


def test_zero_risk_score_means_zero_risk_cost():
    cost = calculate_expected_risk_cost(
        risk_score=0.0, amount=Decimal("50000.00"), risk_cost_multiplier=0.05
    )
    assert cost == Decimal("0.000")


class StubEstimator:

    def __init__(self, probability_by_action: dict[RecoveryAction, float]):
        self._probability_by_action = probability_by_action

    def estimate(self, session, *, context, action, config):
        return ProbabilityEstimate(
            probability=self._probability_by_action[action],
            source_tier="stub", sample_size=999,
        )


def make_config(**overrides) -> RecoveryConfigSnapshot:
    defaults = dict(
        id=None, version=1, merchant_id=None,
        default_probability_by_action={a: 0.1 for a in RecoveryAction},
        action_cost_by_action={
            RecoveryAction.RETRY: Decimal("2.00"),
            RecoveryAction.SEND_RECOVERY_REMINDER: Decimal("0.50"),
            RecoveryAction.SEND_RECOVERY_LINK: Decimal("0.50"),
            RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD: Decimal("1.00"),
        },
        risk_cost_multiplier=0.05, min_sample_size=30, smoothing_alpha=1.0, smoothing_beta=1.0,
    )
    defaults.update(overrides)
    return RecoveryConfigSnapshot(**defaults)


def test_ranks_highest_expected_value_first():
    estimator = StubEstimator({
        RecoveryAction.RETRY: 0.1,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD: 0.7,
    })
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="insufficient_funds",
        payment_method="card", amount=Decimal("1000.00"),
    )

    evaluations = evaluate_candidate_actions(
        session=None, estimator=estimator, context=context,
        candidate_actions=[RecoveryAction.RETRY, RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD],
        risk_score=0.1, config=make_config(),
    )

    assert [e.action for e in evaluations] == [
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD, RecoveryAction.RETRY,
    ]
    assert evaluations[0].expected_recovery_value > evaluations[1].expected_recovery_value


def test_returns_full_ranked_list_not_just_the_winner():
    estimator = StubEstimator({a: 0.3 for a in RecoveryAction})
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"),
    )
    candidates = [
        RecoveryAction.RETRY, RecoveryAction.SEND_RECOVERY_REMINDER,
        RecoveryAction.SEND_RECOVERY_LINK, RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
    ]

    evaluations = evaluate_candidate_actions(
        session=None, estimator=estimator, context=context, candidate_actions=candidates,
        risk_score=0.1, config=make_config(),
    )

    assert len(evaluations) == len(candidates)
    assert {e.action for e in evaluations} == set(candidates)


def test_each_evaluation_carries_its_own_probability_estimate_and_cost_breakdown():
    estimator = StubEstimator({RecoveryAction.RETRY: 0.5})
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("2000.00"),
    )

    [evaluation] = evaluate_candidate_actions(
        session=None, estimator=estimator, context=context,
        candidate_actions=[RecoveryAction.RETRY], risk_score=0.2, config=make_config(),
    )

    assert isinstance(evaluation, ActionEvaluation)
    assert evaluation.probability_estimate.probability == 0.5
    assert evaluation.probability_estimate.source_tier == "stub"
    assert evaluation.action_cost == Decimal("2.00")
    assert evaluation.expected_risk_cost == Decimal("20.000")
    assert evaluation.expected_recovery_value == Decimal("978.000")


def test_higher_risk_score_lowers_expected_value_for_every_candidate():
    estimator = StubEstimator({RecoveryAction.RETRY: 0.5})
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("2000.00"),
    )
    config = make_config()

    [low_risk] = evaluate_candidate_actions(
        session=None, estimator=estimator, context=context,
        candidate_actions=[RecoveryAction.RETRY], risk_score=0.05, config=config,
    )
    [high_risk] = evaluate_candidate_actions(
        session=None, estimator=estimator, context=context,
        candidate_actions=[RecoveryAction.RETRY], risk_score=0.9, config=config,
    )

    assert low_risk.expected_recovery_value > high_risk.expected_recovery_value
