
from decimal import Decimal

from models.enums import RecoveryAction
from services.evaluation.dataset import generate_synthetic_outcomes, persist_synthetic_outcomes
from services.recovery.expected_value import evaluate_candidate_actions
from services.recovery.probability import EmpiricalRecoveryProbabilityEstimator, RecoveryCaseContext
from services.recovery.recovery_config_repository import ensure_default_recovery_config, get_active_recovery_config

CANDIDATE_ACTIONS = [
    RecoveryAction.RETRY,
    RecoveryAction.SEND_RECOVERY_REMINDER,
    RecoveryAction.SEND_RECOVERY_LINK,
    RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
]


def seed_dataset(db_session, n=20000, seed=42):
    outcomes = generate_synthetic_outcomes(seed=seed, n=n)
    persist_synthetic_outcomes(db_session, outcomes)
    ensure_default_recovery_config(db_session)


def test_alternative_payment_method_beats_retry_for_insufficient_funds_end_to_end(db_session):
    seed_dataset(db_session)
    config = get_active_recovery_config(db_session, merchant_id="merchant_1")
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="insufficient_funds",
        payment_method="card", amount=Decimal("2000.00"),
    )

    evaluations = evaluate_candidate_actions(
        db_session, EmpiricalRecoveryProbabilityEstimator(), context=context,
        candidate_actions=CANDIDATE_ACTIONS, risk_score=0.1, config=config,
    )

    ranking = [e.action for e in evaluations]
    assert ranking.index(RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD) < ranking.index(
        RecoveryAction.RETRY
    )
    top = evaluations[0]
    assert top.action is RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD
    assert top.expected_recovery_value > 0
    by_action = {e.action: e for e in evaluations}
    assert top.probability_estimate.sample_size > 0
    assert by_action[RecoveryAction.RETRY].probability_estimate.source_tier != "merchant_specific"


def test_retry_wins_for_a_clean_transient_timeout_end_to_end(db_session):
    seed_dataset(db_session)
    config = get_active_recovery_config(db_session, merchant_id="merchant_1")
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="bank_timeout",
        payment_method="upi", amount=Decimal("2000.00"),
    )

    evaluations = evaluate_candidate_actions(
        db_session, EmpiricalRecoveryProbabilityEstimator(), context=context,
        candidate_actions=CANDIDATE_ACTIONS, risk_score=0.1, config=config,
    )

    assert evaluations[0].action is RecoveryAction.RETRY
    assert evaluations[0].expected_recovery_value > 0


def test_customer_action_failure_favors_reminder_or_link_over_retry_end_to_end(db_session):
    seed_dataset(db_session)
    config = get_active_recovery_config(db_session, merchant_id="merchant_1")
    context = RecoveryCaseContext(
        merchant_id="merchant_1", failure_code="otp_failure",
        payment_method="upi", amount=Decimal("1500.00"),
    )

    evaluations = evaluate_candidate_actions(
        db_session, EmpiricalRecoveryProbabilityEstimator(), context=context,
        candidate_actions=CANDIDATE_ACTIONS, risk_score=0.1, config=config,
    )

    ranking = [e.action for e in evaluations]
    assert ranking[0] in {RecoveryAction.SEND_RECOVERY_REMINDER, RecoveryAction.SEND_RECOVERY_LINK}
    assert ranking.index(ranking[0]) < ranking.index(RecoveryAction.RETRY)


def test_low_sample_merchant_falls_back_but_still_produces_a_reasonable_ranking(db_session):
    seed_dataset(db_session)
    config = get_active_recovery_config(db_session, merchant_id="merchant_never_seen")
    context = RecoveryCaseContext(
        merchant_id="merchant_never_seen", failure_code="insufficient_funds",
        payment_method="card", amount=Decimal("2000.00"),
    )

    evaluations = evaluate_candidate_actions(
        db_session, EmpiricalRecoveryProbabilityEstimator(), context=context,
        candidate_actions=CANDIDATE_ACTIONS, risk_score=0.1, config=config,
    )

    assert evaluations[0].action is RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD
    assert evaluations[0].probability_estimate.source_tier in {"segment", "global_baseline"}
