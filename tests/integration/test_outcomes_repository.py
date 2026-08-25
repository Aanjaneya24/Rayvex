
from decimal import Decimal

from models.enums import RecoveryAction
from services.evaluation.dataset import persist_synthetic_outcomes
from services.evaluation.dataset import GeneratedOutcome
from services.evaluation.outcomes_repository import (
    amount_bucket,
    global_baseline_stats,
    merchant_specific_stats,
    segment_stats,
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


def test_amount_bucket_boundaries():
    assert amount_bucket(Decimal("999.99")) == "under_1k"
    assert amount_bucket(Decimal("1000.00")) == "1k_5k"
    assert amount_bucket(Decimal("4999.99")) == "1k_5k"
    assert amount_bucket(Decimal("5000.00")) == "5k_20k"
    assert amount_bucket(Decimal("19999.99")) == "5k_20k"
    assert amount_bucket(Decimal("20000.00")) == "20k_plus"


def test_merchant_specific_stats_counts_only_the_exact_segment(db_session):
    rows = [
        make_outcome(recovered=True),
        make_outcome(recovered=True),
        make_outcome(recovered=False),
        make_outcome(merchant_id="merchant_2", recovered=True),
        make_outcome(failure_code="gateway_timeout", recovered=True),
        make_outcome(action_taken=RecoveryAction.SEND_RECOVERY_REMINDER, recovered=True),
        make_outcome(amount=Decimal("50000.00"), recovered=True),
    ]
    persist_synthetic_outcomes(db_session, rows)

    stats = merchant_specific_stats(
        db_session, merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"), action=RecoveryAction.RETRY,
    )

    assert stats.total == 3
    assert stats.successes == 2
    assert stats.empirical_rate == 2 / 3


def test_segment_stats_ignores_merchant_but_respects_the_rest(db_session):
    rows = [
        make_outcome(merchant_id="merchant_1", recovered=True),
        make_outcome(merchant_id="merchant_2", recovered=True),
        make_outcome(merchant_id="merchant_3", recovered=False),
        make_outcome(merchant_id="merchant_1", failure_code="network_error", recovered=True),
    ]
    persist_synthetic_outcomes(db_session, rows)

    stats = segment_stats(
        db_session, failure_code="bank_timeout", payment_method="upi",
        amount=Decimal("1000.00"), action=RecoveryAction.RETRY,
    )

    assert stats.total == 3
    assert stats.successes == 2


def test_global_baseline_stats_ignores_merchant_method_and_amount_but_keeps_failure_code(db_session):
    rows = [
        make_outcome(action_taken=RecoveryAction.RETRY, failure_code="bank_timeout",
                     payment_method="upi", recovered=True),
        make_outcome(action_taken=RecoveryAction.RETRY, failure_code="bank_timeout",
                     payment_method="card", amount=Decimal("99999.00"), recovered=False),
        make_outcome(action_taken=RecoveryAction.RETRY, failure_code="gateway_timeout",
                     recovered=True),
        make_outcome(action_taken=RecoveryAction.SEND_RECOVERY_REMINDER,
                     failure_code="bank_timeout", recovered=True),
    ]
    persist_synthetic_outcomes(db_session, rows)

    stats = global_baseline_stats(db_session, failure_code="bank_timeout", action=RecoveryAction.RETRY)

    assert stats.total == 2
    assert stats.successes == 1


def test_stats_with_no_matching_rows_is_zero_not_an_error(db_session):
    stats = merchant_specific_stats(
        db_session, merchant_id="nonexistent", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("1000.00"), action=RecoveryAction.RETRY,
    )
    assert stats.total == 0
    assert stats.successes == 0
    assert stats.empirical_rate is None
