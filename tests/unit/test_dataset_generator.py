
from decimal import Decimal

from models.enums import RecoveryAction
from services.evaluation.dataset import (
    FAILURE_TAXONOMY,
    PAYMENT_METHODS,
    true_success_probability,
    generate_synthetic_outcomes,
)


def test_same_seed_and_n_produce_identical_output():
    a = generate_synthetic_outcomes(seed=42, n=200)
    b = generate_synthetic_outcomes(seed=42, n=200)
    assert a == b


def test_different_seeds_produce_different_output():
    a = generate_synthetic_outcomes(seed=1, n=200)
    b = generate_synthetic_outcomes(seed=2, n=200)
    assert a != b


def test_generates_the_requested_count():
    outcomes = generate_synthetic_outcomes(seed=7, n=137)
    assert len(outcomes) == 137


def test_every_row_is_seed_tagged_with_the_generator_seed():
    outcomes = generate_synthetic_outcomes(seed=99, n=50)
    assert all(o.seed == 99 for o in outcomes)


def test_covers_every_failure_category_and_payment_method_at_reasonable_n():
    outcomes = generate_synthetic_outcomes(seed=42, n=3000)
    categories_seen = {o.failure_category for o in outcomes}
    methods_seen = {o.payment_method for o in outcomes}
    assert categories_seen == set(FAILURE_TAXONOMY.keys())
    assert methods_seen == set(PAYMENT_METHODS)


def test_failure_codes_always_belong_to_their_declared_category():
    outcomes = generate_synthetic_outcomes(seed=42, n=1000)
    for o in outcomes:
        assert o.failure_code in FAILURE_TAXONOMY[o.failure_category]


def test_amounts_are_positive_decimals():
    outcomes = generate_synthetic_outcomes(seed=42, n=200)
    assert all(isinstance(o.amount, Decimal) and o.amount > 0 for o in outcomes)


def test_retry_beats_alternatives_for_a_transient_failure():
    common_kwargs = dict(
        failure_category="transient", payment_method="upi",
        retry_count_at_action_time=0, risk_score=0.1,
    )
    retry_p = true_success_probability(action=RecoveryAction.RETRY, **common_kwargs)
    alt_p = true_success_probability(
        action=RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD, **common_kwargs
    )
    assert retry_p > alt_p


def test_alternative_payment_method_beats_retry_for_insufficient_funds():
    common_kwargs = dict(
        failure_category="payment_method", payment_method="card",
        retry_count_at_action_time=0, risk_score=0.1,
    )
    retry_p = true_success_probability(action=RecoveryAction.RETRY, **common_kwargs)
    alt_p = true_success_probability(
        action=RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD, **common_kwargs
    )
    assert alt_p > retry_p
    assert retry_p < 0.1


def test_retry_probability_decays_with_higher_retry_count():
    p0 = true_success_probability(
        failure_category="transient", action=RecoveryAction.RETRY, payment_method="upi",
        retry_count_at_action_time=0, risk_score=0.1,
    )
    p2 = true_success_probability(
        failure_category="transient", action=RecoveryAction.RETRY, payment_method="upi",
        retry_count_at_action_time=2, risk_score=0.1,
    )
    assert p0 > p2


def test_higher_risk_score_reduces_probability_for_any_action():
    low_risk = true_success_probability(
        failure_category="transient", action=RecoveryAction.RETRY, payment_method="upi",
        retry_count_at_action_time=0, risk_score=0.05,
    )
    high_risk = true_success_probability(
        failure_category="transient", action=RecoveryAction.RETRY, payment_method="upi",
        retry_count_at_action_time=0, risk_score=0.9,
    )
    assert low_risk > high_risk


def test_risk_category_probability_is_low_regardless_of_action():
    for action in [
        RecoveryAction.RETRY, RecoveryAction.SEND_RECOVERY_REMINDER,
        RecoveryAction.SEND_RECOVERY_LINK, RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
    ]:
        p = true_success_probability(
            failure_category="risk", action=action, payment_method="upi",
            retry_count_at_action_time=0, risk_score=0.5,
        )
        assert p < 0.15


def test_probability_is_always_within_configured_bounds():
    outcomes = generate_synthetic_outcomes(seed=42, n=500)
    for o in outcomes:
        p = true_success_probability(
            failure_category=o.failure_category, action=o.action_taken,
            payment_method=o.payment_method,
            retry_count_at_action_time=o.retry_count_at_action_time, risk_score=o.risk_score,
        )
        assert 0.01 <= p <= 0.95
