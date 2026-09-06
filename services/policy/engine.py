
from models.enums import PolicyVerdictType, RecoveryAction
from services.policy.context import PolicyConfigSnapshot, PolicyContext, PolicyVerdict

COMMUNICATION_ACTIONS = frozenset(
    {
        RecoveryAction.SEND_RECOVERY_REMINDER,
        RecoveryAction.SEND_RECOVERY_LINK,
        RecoveryAction.SUGGEST_ALTERNATIVE_PAYMENT_METHOD,
    }
)

INTERVENTION_ACTIONS = frozenset(RecoveryAction) - {
    RecoveryAction.STOP,
    RecoveryAction.ESCALATE_TO_HUMAN,
}


def evaluate(context: PolicyContext, config: PolicyConfigSnapshot) -> PolicyVerdict:
    if context.suspicious_velocity:
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.FORCE_ACTION,
            resulting_action=RecoveryAction.STOP,
            rule_id="suspicious_velocity_stop_and_escalate",
            reason=(
                "Suspicious velocity detected for this customer/case: "
                "automation stopped and the case requires human escalation, "
                "regardless of the proposed action."
            ),
            requires_escalation=True,
        )

    if context.retry_count >= config.max_retry_count:
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.FORCE_ACTION,
            resulting_action=RecoveryAction.STOP,
            rule_id="max_retry_count_exceeded",
            reason=(
                f"Retry count ({context.retry_count}) has reached the configured "
                f"maximum ({config.max_retry_count}); stopping unconditionally."
            ),
        )

    if (
        context.proposed_action in INTERVENTION_ACTIONS
        and context.intervention_count >= config.max_interventions_per_case
    ):
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.FORCE_ACTION,
            resulting_action=RecoveryAction.STOP,
            rule_id="max_interventions_per_case_exceeded",
            reason=(
                f"This case has already had {context.intervention_count} automated "
                f"interventions, at the configured cap of "
                f"{config.max_interventions_per_case}; stopping."
            ),
        )

    if (
        context.proposed_action in INTERVENTION_ACTIONS
        and context.daily_attempts_count >= config.max_daily_attempts_per_customer
    ):
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.DENY,
            resulting_action=None,
            rule_id="max_daily_attempts_per_customer_exceeded",
            reason=(
                f"This customer has already had {context.daily_attempts_count} "
                f"recovery attempts today, at the configured daily cap of "
                f"{config.max_daily_attempts_per_customer}."
            ),
        )

    if context.proposed_action in INTERVENTION_ACTIONS and context.amount > config.max_automated_recovery_amount:
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.DENY,
            resulting_action=None,
            rule_id="amount_exceeds_max_automated_recovery_amount",
            reason=(
                f"Amount {context.amount} exceeds the maximum automated recovery "
                f"amount ({config.max_automated_recovery_amount}); no automated "
                f"action is authorized above this ceiling."
            ),
            requires_escalation=True,
        )

    if context.proposed_action in INTERVENTION_ACTIONS and context.amount > config.high_value_threshold:
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.FORCE_ACTION,
            resulting_action=RecoveryAction.ESCALATE_TO_HUMAN,
            rule_id="high_value_requires_human_approval",
            reason=(
                f"Amount {context.amount} exceeds the high-value threshold "
                f"({config.high_value_threshold}); requires human approval "
                f"before any action."
            ),
            requires_escalation=True,
        )

    if (
        context.proposed_action is RecoveryAction.RETRY
        and context.failure_code in config.prohibited_retry_failure_codes
    ):
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.DENY,
            resulting_action=None,
            rule_id="prohibited_retry_failure_code",
            reason=(
                f"Failure code '{context.failure_code}' is configured as a "
                f"prohibited-retry category; blind retry is never allowed for "
                f"it, regardless of retry count, amount, risk, or cooldown."
            ),
        )

    allowed_for_failure = config.allowed_actions_by_failure_code.get(context.failure_code)
    if (
        allowed_for_failure is not None
        and context.proposed_action not in allowed_for_failure
        and context.proposed_action is not RecoveryAction.STOP
    ):
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.DENY,
            resulting_action=None,
            rule_id="action_not_allowed_for_failure_code",
            reason=(
                f"'{context.proposed_action.value}' is not in the configured "
                f"allowed-action list for failure code '{context.failure_code}'."
            ),
        )

    if context.proposed_action in COMMUNICATION_ACTIONS and not (
        config.allowed_communication_hours_start
        <= context.current_hour
        < config.allowed_communication_hours_end
    ):
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.DENY,
            resulting_action=None,
            rule_id="outside_allowed_communication_hours",
            reason=(
                f"Current hour ({context.current_hour}:00) is outside the "
                f"configured customer-communication window "
                f"({config.allowed_communication_hours_start}:00-"
                f"{config.allowed_communication_hours_end}:00)."
            ),
        )

    if context.proposed_action is RecoveryAction.RETRY and not context.cooldown_satisfied:
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.DENY,
            resulting_action=None,
            rule_id="cooldown_not_satisfied",
            reason=(
                f"The configured cooldown ({config.cooldown_seconds}s) between "
                f"retries has not yet elapsed for this case."
            ),
        )

    if (
        context.proposed_action is RecoveryAction.RETRY
        and context.risk_score >= config.risk_score_threshold
    ):
        return PolicyVerdict(
            verdict_type=PolicyVerdictType.DENY,
            resulting_action=None,
            rule_id="risk_score_exceeds_threshold",
            reason=(
                f"Risk score ({context.risk_score:.2f}) meets or exceeds the "
                f"configured threshold ({config.risk_score_threshold:.2f}) for "
                f"an automated retry."
            ),
        )

    return PolicyVerdict(
        verdict_type=PolicyVerdictType.ALLOW,
        resulting_action=context.proposed_action,
        rule_id="policy_conditions_satisfied",
        reason=f"'{context.proposed_action.value}' satisfies every configured policy check.",
    )
