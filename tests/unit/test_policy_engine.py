
import uuid
from decimal import Decimal

import pytest

from models.enums import PolicyVerdictType, RecoveryAction
from services.policy.context import PolicyConfigSnapshot, PolicyContext
from services.policy.engine import evaluate

CONFIG_ID = uuid.uuid4()


def make_config(**overrides) -> PolicyConfigSnapshot:
    defaults = dict(
        id=CONFIG_ID,
        version=1,
        merchant_id=None,
        max_retry_count=3,
        cooldown_seconds=300,
        max_automated_recovery_amount=Decimal("50000.00"),
        max_daily_attempts_per_customer=5,
        prohibited_retry_failure_codes=frozenset({"insufficient_funds"}),
        suspicious_velocity_threshold=5,
        suspicious_velocity_window_seconds=600,
        high_value_threshold=Decimal("20000.00"),
        allowed_actions_by_failure_code={},
        allowed_communication_hours_start=8,
        allowed_communication_hours_end=21,
        max_interventions_per_case=5,
        risk_score_threshold=0.7,
    )
    defaults.update(overrides)
    return PolicyConfigSnapshot(**defaults)


def make_context(**overrides) -> PolicyContext:
    defaults = dict(
        failure_code="bank_timeout",
        proposed_action=RecoveryAction.RETRY,
        amount=Decimal("1000.00"),
        retry_count=0,
        intervention_count=0,
        daily_attempts_count=0,
        risk_score=0.1,
        cooldown_satisfied=True,
        suspicious_velocity=False,
        current_hour=12,
    )
    defaults.update(overrides)
    return PolicyContext(**defaults)


def test_example_1_transient_timeout_retry_allowed_when_all_conditions_met():
    config = make_config()
    context = make_context(
        failure_code="bank_timeout",
        proposed_action=RecoveryAction.RETRY,
        retry_count=2,
        amount=Decimal("1000.00"),
        risk_score=0.2,
        cooldown_satisfied=True,
    )

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.ALLOW
    assert verdict.resulting_action is RecoveryAction.RETRY
    assert verdict.rule_id == "policy_conditions_satisfied"


@pytest.mark.parametrize(
    "field,value",
    [
        ("retry_count", 3),
        ("risk_score", 0.9),
        ("cooldown_satisfied", False),
    ],
)
def test_example_1_retry_denied_when_any_single_condition_fails(field, value):
    config = make_config()
    context = make_context(**{field: value})

    verdict = evaluate(context, config)

    assert verdict.verdict_type is not PolicyVerdictType.ALLOW


def test_example_1_retry_denied_when_amount_exceeds_limit():
    config = make_config()
    context = make_context(amount=Decimal("999999.00"))

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.DENY
    assert verdict.rule_id == "amount_exceeds_max_automated_recovery_amount"


@pytest.mark.parametrize("retry_count", [0, 1, 2])
@pytest.mark.parametrize("amount", [Decimal("100.00"), Decimal("15000.00")])
def test_example_2_insufficient_funds_never_blind_retried_regardless_of_other_factors(
    retry_count, amount
):
    config = make_config()
    context = make_context(
        failure_code="insufficient_funds",
        proposed_action=RecoveryAction.RETRY,
        retry_count=retry_count,
        amount=amount,
        risk_score=0.1,
        cooldown_satisfied=True,
        suspicious_velocity=False,
    )

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.DENY
    assert verdict.rule_id == "prohibited_retry_failure_code"
    assert verdict.resulting_action is None


def test_example_2_insufficient_funds_does_not_block_non_retry_actions():
    config = make_config()
    context = make_context(
        failure_code="insufficient_funds",
        proposed_action=RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
        current_hour=12,
    )

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.ALLOW


@pytest.mark.parametrize(
    "proposed_action",
    [RecoveryAction.RETRY, RecoveryAction.SEND_RECOVERY_REMINDER, RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD],
)
def test_example_3_suspicious_velocity_forces_stop_and_escalation(proposed_action):
    config = make_config()
    context = make_context(proposed_action=proposed_action, suspicious_velocity=True)

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.FORCE_ACTION
    assert verdict.resulting_action is RecoveryAction.STOP
    assert verdict.rule_id == "suspicious_velocity_stop_and_escalate"
    assert verdict.requires_escalation is True


def test_example_3_suspicious_velocity_takes_precedence_over_retry_exhaustion():
    config = make_config()
    context = make_context(retry_count=5, suspicious_velocity=True)

    verdict = evaluate(context, config)

    assert verdict.rule_id == "suspicious_velocity_stop_and_escalate"
    assert verdict.requires_escalation is True


@pytest.mark.parametrize("retry_count", [3, 4, 10])
def test_example_4_retry_count_at_or_above_max_stops_unconditionally(retry_count):
    config = make_config(max_retry_count=3)
    context = make_context(retry_count=retry_count)

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.FORCE_ACTION
    assert verdict.resulting_action is RecoveryAction.STOP
    assert verdict.rule_id == "max_retry_count_exceeded"


def test_example_4_stops_even_when_proposed_action_is_not_retry():
    config = make_config(max_retry_count=3)
    context = make_context(
        retry_count=3, proposed_action=RecoveryAction.SEND_RECOVERY_REMINDER,
        current_hour=12,
    )

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.FORCE_ACTION
    assert verdict.resulting_action is RecoveryAction.STOP
    assert verdict.rule_id == "max_retry_count_exceeded"


def test_example_4_does_not_require_escalation_unlike_example_3():
    config = make_config()
    context = make_context(retry_count=3)

    verdict = evaluate(context, config)

    assert verdict.requires_escalation is False


def test_stop_is_never_blocked_by_amount_thresholds():
    config = make_config()
    context = make_context(
        proposed_action=RecoveryAction.STOP,
        amount=Decimal("999999.00"),
        retry_count=0,
        intervention_count=0,
        daily_attempts_count=0,
        suspicious_velocity=False,
    )

    verdict = evaluate(context, config)

    assert verdict.verdict_type is PolicyVerdictType.ALLOW
    assert verdict.resulting_action is RecoveryAction.STOP


def test_stop_is_never_blocked_even_under_every_other_adverse_condition():
    config = make_config()
    context = make_context(
        proposed_action=RecoveryAction.STOP,
        failure_code="insufficient_funds",
        retry_count=10,
        amount=Decimal("999999.00"),
        suspicious_velocity=True,
    )

    verdict = evaluate(context, config)

    assert verdict.resulting_action is RecoveryAction.STOP
