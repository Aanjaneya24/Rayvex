
from decimal import Decimal

from models.ab_experiment_run import ABExperimentRun
from models.enums import RecoveryAction
from services.evaluation.ab_testing import (
    RESULT_INSUFFICIENT_EVIDENCE,
    RESULT_NOT_SIGNIFICANT,
    RESULT_WINNER_A,
    RESULT_WINNER_B,
    run_ab_experiment,
)
from services.evaluation.dataset import GeneratedOutcome, persist_synthetic_outcomes
from services.recovery.expected_value import RecoveryConfigSnapshot


def make_config(**overrides) -> RecoveryConfigSnapshot:
    defaults = dict(
        id=None, version=1, merchant_id=None,
        default_probability_by_action={a: 0.13 for a in RecoveryAction},
        action_cost_by_action={a: Decimal("2.00") for a in RecoveryAction},
        risk_cost_multiplier=0.05, min_sample_size=5,
        smoothing_alpha=1.0, smoothing_beta=1.0,
    )
    defaults.update(overrides)
    return RecoveryConfigSnapshot(**defaults)


def make_outcome(**overrides) -> GeneratedOutcome:
    defaults = dict(
        seed=1, merchant_id="merchant_1", customer_id="cust_1", payment_method="upi",
        failure_category="transient", failure_code="bank_timeout", amount=Decimal("1000.00"),
        retry_count_at_action_time=0, risk_score=0.1, action_taken=RecoveryAction.RETRY,
        recovered=True,
    )
    defaults.update(overrides)
    return GeneratedOutcome(**defaults)


def test_insufficient_evidence_when_sample_too_small(db_session):
    rows = [make_outcome(action_taken=RecoveryAction.RETRY, recovered=True) for _ in range(5)]
    rows += [make_outcome(action_taken=RecoveryAction.SEND_RECOVERY_REMINDER, recovered=True) for _ in range(5)]
    persist_synthetic_outcomes(db_session, rows)

    result = run_ab_experiment(
        db_session, failure_code="bank_timeout", payment_method="upi",
        action_a=RecoveryAction.RETRY, action_b=RecoveryAction.SEND_RECOVERY_REMINDER,
        config=make_config(), min_sample_size=100,
    )

    assert result.result == RESULT_INSUFFICIENT_EVIDENCE
    assert result.p_value is None


def test_not_significant_when_rates_are_close(db_session):
    rows = []
    for i in range(60):
        rows.append(make_outcome(action_taken=RecoveryAction.RETRY, recovered=(i % 2 == 0)))
    for i in range(60):
        rows.append(make_outcome(action_taken=RecoveryAction.SEND_RECOVERY_REMINDER, recovered=(i % 2 == 0)))
    persist_synthetic_outcomes(db_session, rows)

    result = run_ab_experiment(
        db_session, failure_code="bank_timeout", payment_method="upi",
        action_a=RecoveryAction.RETRY, action_b=RecoveryAction.SEND_RECOVERY_REMINDER,
        config=make_config(), min_sample_size=30,
    )

    assert result.result == RESULT_NOT_SIGNIFICANT
    assert result.p_value is not None
    assert result.p_value >= 0.05


def test_declares_a_real_winner_with_a_strong_and_clear_difference(db_session):
    rows = []
    for i in range(200):
        rows.append(make_outcome(action_taken=RecoveryAction.RETRY, recovered=(i % 10 != 0)))
    for i in range(200):
        rows.append(make_outcome(action_taken=RecoveryAction.SEND_RECOVERY_REMINDER, recovered=(i % 10 == 0)))
    persist_synthetic_outcomes(db_session, rows)

    result = run_ab_experiment(
        db_session, failure_code="bank_timeout", payment_method="upi",
        action_a=RecoveryAction.RETRY, action_b=RecoveryAction.SEND_RECOVERY_REMINDER,
        config=make_config(), min_sample_size=30,
    )

    assert result.result == RESULT_WINNER_A
    assert result.p_value < 0.05
    assert result.arm_a.recovery_rate > result.arm_b.recovery_rate


def test_experiment_run_is_persisted(db_session):
    rows = [make_outcome(action_taken=RecoveryAction.RETRY, recovered=True) for _ in range(40)]
    rows += [make_outcome(action_taken=RecoveryAction.SEND_RECOVERY_REMINDER, recovered=False) for _ in range(40)]
    persist_synthetic_outcomes(db_session, rows)

    result = run_ab_experiment(
        db_session, failure_code="bank_timeout", payment_method="upi",
        action_a=RecoveryAction.RETRY, action_b=RecoveryAction.SEND_RECOVERY_REMINDER,
        config=make_config(), min_sample_size=30,
    )

    persisted = db_session.get(ABExperimentRun, result.ab_experiment_run_id)
    assert persisted is not None
    assert persisted.result == result.result
    assert persisted.sample_size_a == result.arm_a.sample_size


def test_cost_per_recovered_rupee_is_none_when_nothing_recovered(db_session):
    rows = [make_outcome(action_taken=RecoveryAction.RETRY, recovered=False) for _ in range(40)]
    rows += [make_outcome(action_taken=RecoveryAction.SEND_RECOVERY_REMINDER, recovered=False) for _ in range(40)]
    persist_synthetic_outcomes(db_session, rows)

    result = run_ab_experiment(
        db_session, failure_code="bank_timeout", payment_method="upi",
        action_a=RecoveryAction.RETRY, action_b=RecoveryAction.SEND_RECOVERY_REMINDER,
        config=make_config(), min_sample_size=30,
    )

    assert result.cost_per_recovered_rupee_a is None
    assert result.cost_per_recovered_rupee_b is None
