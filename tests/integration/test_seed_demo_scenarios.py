
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from models.enums import CaseState
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config

import seed_demo


def _setup(db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)


def test_scenario_1_upi_timeout_reaches_recovered(db_session, redis_client):
    _setup(db_session)
    outcome = seed_demo.scenario_1_upi_timeout_retry_recovered(db_session, redis_client, live=False)
    assert outcome.case.current_state is CaseState.RECOVERED


def test_scenario_2_insufficient_funds_reaches_recovered_via_alternative(db_session, redis_client):
    _setup(db_session)
    outcome = seed_demo.scenario_2_insufficient_funds_alternative_recovered(db_session, redis_client, live=False)
    assert outcome.case.current_state is CaseState.RECOVERED
    assert outcome.decision.action.value == "SUGGEST_ALTERNATIVE_PAYMENT_METHOD"


def test_scenario_4_repeated_failure_is_stopped_by_policy(db_session, redis_client):
    _setup(db_session)
    gate_result = seed_demo.scenario_4_repeated_failure_policy_stops(db_session, redis_client, live=False)
    assert gate_result.approved is False
    assert gate_result.policy_decision.rule_id == "max_retry_count_exceeded"


def test_scenario_5_suspicious_velocity_is_stopped_with_escalation_flagged(db_session, redis_client):
    _setup(db_session)
    gate_result = seed_demo.scenario_5_suspicious_velocity_escalation(db_session, redis_client, live=False)
    assert gate_result.approved is False
    assert gate_result.policy_decision.requires_escalation is True


def test_scenario_6_duplicate_webhook_is_idempotent(db_session, redis_client):
    _setup(db_session)
    first, second = seed_demo.scenario_6_duplicate_webhook(db_session, redis_client, live=False)
    assert first.status == "processed"
    assert second.status == "duplicate"


def test_scenario_7_reconciliation_reaches_recovered(db_session, redis_client):
    _setup(db_session)
    reconciliation = seed_demo.scenario_7_failed_captured_reconciliation(db_session, redis_client, live=False)
    assert reconciliation.outcome.value == "RECOVERED"


def test_scenario_8_prompt_injection_still_blocked(db_session, redis_client):
    _setup(db_session)
    outcome = seed_demo.scenario_8_prompt_injection_ignored(db_session, redis_client, live=False)
    assert outcome.case.current_state is CaseState.STOPPED
    assert outcome.gate_result.policy_decision.rule_id == "prohibited_retry_failure_code"


def test_scenario_9_verification_error_stays_pending(db_session, redis_client):
    _setup(db_session)
    outcome = seed_demo.scenario_9_verification_stays_pending(db_session, redis_client, live=False)
    assert outcome.case.current_state is CaseState.VERIFICATION_PENDING
    assert outcome.verification_result.outcome.value == "ERROR"


def test_scenario_10_amount_mismatch_reaches_escalated(db_session, redis_client):
    _setup(db_session)
    reconciliation = seed_demo.scenario_10_captured_amount_mismatch_escalated(db_session, redis_client, live=False)
    assert reconciliation.outcome.value == "ESCALATED"
    assert reconciliation.transition.to_state is CaseState.ESCALATED


def test_scenario_11_batch_evaluation_produces_a_real_comparison(db_session, redis_client):
    _setup(db_session)
    run = seed_demo.scenario_11_batch_evaluation(db_session, redis_client, live=False, n=80)
    assert run.case_count == 80
    assert run.naive_retry_metrics["revenue_at_risk"] > 0
