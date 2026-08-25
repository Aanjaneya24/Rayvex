
from decimal import Decimal

import pytest

from models.enums import RecoveryAction
from services.evaluation.dataset import generate_synthetic_outcomes, persist_synthetic_outcomes
from services.ml.estimator import LightGBMProbabilityEstimator, NoActiveModelError
from services.ml.training import train_and_persist_model
from services.recovery.expected_value import RecoveryConfigSnapshot
from services.recovery.probability import RecoveryCaseContext


def make_config(**overrides) -> RecoveryConfigSnapshot:
    defaults = dict(
        id=None, version=1, merchant_id=None,
        default_probability_by_action={a: 0.13 for a in RecoveryAction},
        action_cost_by_action={a: Decimal("1.00") for a in RecoveryAction},
        risk_cost_multiplier=0.05, min_sample_size=5,
        smoothing_alpha=1.0, smoothing_beta=1.0,
    )
    defaults.update(overrides)
    return RecoveryConfigSnapshot(**defaults)


def test_estimator_raises_without_a_trained_model(db_session):
    estimator = LightGBMProbabilityEstimator()
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"),
    )
    with pytest.raises(NoActiveModelError):
        estimator.estimate(db_session, context=context, action=RecoveryAction.RETRY, config=make_config())


def test_estimator_returns_probability_in_valid_range(db_session):
    outcomes = generate_synthetic_outcomes(seed=42, n=3000)
    persist_synthetic_outcomes(db_session, outcomes)
    train_and_persist_model(db_session, seed=42)

    estimator = LightGBMProbabilityEstimator()
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"),
    )
    estimate = estimator.estimate(db_session, context=context, action=RecoveryAction.RETRY, config=make_config())

    assert 0.0 < estimate.probability < 1.0
    assert estimate.source_tier == "ml_lightgbm"
    assert estimate.sample_size == 3000


def test_estimator_distinguishes_well_matched_from_mismatched_action(db_session):
    outcomes = generate_synthetic_outcomes(seed=43, n=4000)
    persist_synthetic_outcomes(db_session, outcomes)
    train_and_persist_model(db_session, seed=43)

    estimator = LightGBMProbabilityEstimator()
    good_fit = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"),
    )
    bad_fit = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="insufficient_funds",
        payment_method="upi", amount=Decimal("1000.00"),
    )
    good_estimate = estimator.estimate(db_session, context=good_fit, action=RecoveryAction.RETRY, config=make_config())
    bad_estimate = estimator.estimate(db_session, context=bad_fit, action=RecoveryAction.RETRY, config=make_config())

    assert good_estimate.probability > bad_estimate.probability


def test_explain_case_returns_per_feature_contributions(db_session):
    outcomes = generate_synthetic_outcomes(seed=44, n=3000)
    persist_synthetic_outcomes(db_session, outcomes)
    train_and_persist_model(db_session, seed=44)

    estimator = LightGBMProbabilityEstimator()
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"),
    )
    explanation = estimator.explain_case(db_session, context=context, action=RecoveryAction.RETRY)

    assert set(explanation.contributions.keys()) == {
        "merchant_id", "failure_code", "payment_method", "action_taken", "amount",
    }
    assert 0.0 < explanation.predicted_probability < 1.0


def test_probability_factory_selects_backend_by_env(db_session, monkeypatch):
    from services.recovery.probability import EmpiricalRecoveryProbabilityEstimator
    from services.recovery.probability_factory import build_probability_estimator

    monkeypatch.delenv("RECOVERY_PROBABILITY_ESTIMATOR", raising=False)
    assert isinstance(build_probability_estimator(), EmpiricalRecoveryProbabilityEstimator)

    monkeypatch.setenv("RECOVERY_PROBABILITY_ESTIMATOR", "lightgbm")
    assert isinstance(build_probability_estimator(), LightGBMProbabilityEstimator)

    monkeypatch.setenv("RECOVERY_PROBABILITY_ESTIMATOR", "bogus")
    with pytest.raises(ValueError):
        build_probability_estimator()
