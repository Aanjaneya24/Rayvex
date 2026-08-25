
from decimal import Decimal

import pytest

from models.enums import RecoveryAction
from services.evaluation.dataset import GeneratedOutcome, persist_synthetic_outcomes
from services.recovery.expected_value import RecoveryConfigSnapshot
from services.recovery.probability import EmpiricalRecoveryProbabilityEstimator, RecoveryCaseContext

CONTEXT = RecoveryCaseContext(
    merchant_id="merchant_1", failure_code="bank_timeout",
    payment_method="upi", amount=Decimal("1000.00"),
)


def make_outcome(**overrides) -> GeneratedOutcome:
    defaults = dict(
        seed=1, merchant_id="merchant_1", customer_id="cust_1", payment_method="upi",
        failure_category="transient", failure_code="bank_timeout", amount=Decimal("1000.00"),
        retry_count_at_action_time=0, risk_score=0.1, action_taken=RecoveryAction.RETRY,
        recovered=True,
    )
    defaults.update(overrides)
    return GeneratedOutcome(**defaults)


def make_config(**overrides) -> RecoveryConfigSnapshot:
    defaults = dict(
        id=None, version=1, merchant_id=None,
        default_probability_by_action={a: 0.13 for a in RecoveryAction},
        action_cost_by_action={a: Decimal("1.00") for a in RecoveryAction},
        risk_cost_multiplier=0.05,
        min_sample_size=5,
        smoothing_alpha=1.0, smoothing_beta=1.0,
    )
    defaults.update(overrides)
    return RecoveryConfigSnapshot(**defaults)


def test_merchant_specific_tier_wins_when_it_has_enough_samples(db_session):
    rows = [make_outcome(recovered=(i < 4)) for i in range(6)]
    persist_synthetic_outcomes(db_session, rows)

    estimator = EmpiricalRecoveryProbabilityEstimator()
    estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.RETRY, config=make_config(),
    )

    assert estimate.source_tier == "merchant_specific"
    assert estimate.sample_size == 6
    assert estimate.probability == pytest.approx(5 / 8)


def test_falls_back_to_segment_when_merchant_specific_is_insufficient(db_session):
    rows = [make_outcome(merchant_id="merchant_1", recovered=True) for _ in range(2)]
    rows += [make_outcome(merchant_id="merchant_2", recovered=(i < 3)) for i in range(5)]
    persist_synthetic_outcomes(db_session, rows)

    estimator = EmpiricalRecoveryProbabilityEstimator()
    estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.RETRY, config=make_config(),
    )

    assert estimate.source_tier == "segment"
    assert estimate.sample_size == 7
    assert estimate.probability == pytest.approx((5 + 1) / (7 + 1 + 1))


def test_falls_back_to_global_baseline_when_segment_is_insufficient(db_session):
    rows = [make_outcome(recovered=True) for _ in range(2)]
    rows += [
        make_outcome(failure_code="bank_timeout", payment_method="card",
                     amount=Decimal("99999.00"), recovered=(i < 4))
        for i in range(6)
    ]
    persist_synthetic_outcomes(db_session, rows)

    estimator = EmpiricalRecoveryProbabilityEstimator()
    estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.RETRY, config=make_config(),
    )

    assert estimate.source_tier == "global_baseline"
    assert estimate.sample_size == 8
    assert estimate.probability == pytest.approx((6 + 1) / (8 + 1 + 1))


def test_global_baseline_does_not_leak_across_different_failure_codes(db_session):
    rows = [make_outcome(recovered=True), make_outcome(recovered=False)]
    rows += [
        make_outcome(failure_code="gateway_timeout", payment_method="card",
                     amount=Decimal("99999.00"), recovered=True)
        for _ in range(20)
    ]
    persist_synthetic_outcomes(db_session, rows)

    estimator = EmpiricalRecoveryProbabilityEstimator()
    estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.RETRY, config=make_config(),
    )

    assert estimate.source_tier == "deterministic_default"


def test_falls_back_to_deterministic_default_when_even_global_is_insufficient(db_session):
    rows = [make_outcome(recovered=True), make_outcome(recovered=False)]
    persist_synthetic_outcomes(db_session, rows)

    config = make_config()
    estimator = EmpiricalRecoveryProbabilityEstimator()
    estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.RETRY, config=config,
    )

    assert estimate.source_tier == "deterministic_default"
    assert estimate.sample_size == 0
    assert estimate.probability == config.default_probability_by_action[RecoveryAction.RETRY]


def test_deterministic_default_used_with_zero_data_at_all(db_session):
    config = make_config()
    estimator = EmpiricalRecoveryProbabilityEstimator()
    estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.SEND_RECOVERY_REMINDER, config=config,
    )

    assert estimate.source_tier == "deterministic_default"
    assert estimate.probability == config.default_probability_by_action[
        RecoveryAction.SEND_RECOVERY_REMINDER
    ]


def test_different_actions_are_scored_independently(db_session):
    rows = [make_outcome(action_taken=RecoveryAction.RETRY, recovered=True) for _ in range(10)]
    persist_synthetic_outcomes(db_session, rows)

    estimator = EmpiricalRecoveryProbabilityEstimator()
    retry_estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.RETRY, config=make_config(),
    )
    reminder_estimate = estimator.estimate(
        db_session, context=CONTEXT, action=RecoveryAction.SEND_RECOVERY_REMINDER,
        config=make_config(),
    )

    assert retry_estimate.source_tier == "merchant_specific"
    assert reminder_estimate.source_tier == "deterministic_default"
