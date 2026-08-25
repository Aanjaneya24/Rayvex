
import uuid
from decimal import Decimal

from models.enums import CaseState, CaseType, PolicyVerdictType, RecoveryAction
from services.policy.config_repository import ensure_default_global_config
from services.policy.redis_guards import record_action_attempt
from services.recovery.action_gate import check_action_before_execution
from services.recovery.state_machine import RecoveryStateMachine


def _execute_and_fail_one_retry_attempt(sm: RecoveryStateMachine, case_id):
    correlation_id = uuid.uuid4()
    sm.transition(
        case_id, to_state=CaseState.ACTION_EXECUTED, reason="RETRY executed",
        actor="system:action_executor", correlation_id=correlation_id,
        evidence={"action": RecoveryAction.RETRY.value},
    )
    sm.transition(
        case_id, to_state=CaseState.VERIFICATION_PENDING, reason="awaiting verification",
        actor="system:action_executor", correlation_id=correlation_id,
    )
    sm.transition(
        case_id, to_state=CaseState.FAILED, reason="verification found no successful payment state",
        actor="system:verification", correlation_id=correlation_id,
    )


def test_retry_count_accumulates_across_the_loop_and_the_fourth_attempt_is_stopped(
    db_session, redis_client
):
    ensure_default_global_config(db_session)
    sm = RecoveryStateMachine(db_session)

    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE,
        merchant_id="merchant_1", customer_id="cust_loop_1", payment_id="pay_1",
        order_id="order_1", amount=Decimal("1000.00"), currency="INR",
        payment_method="upi", failure_code="bank_timeout", failure_reason="payment_failed",
        reason="payment.failed webhook received", actor="system:ingestion",
    )
    for to_state in [
        CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION,
    ]:
        sm.transition(
            case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
            correlation_id=uuid.uuid4(),
        )

    expected_retry_counts_seen = []

    for attempt_number in range(1, 4):
        sm.transition(
            case.id, to_state=CaseState.ACTION_PENDING, reason="RETRY selected",
            actor="agent:llm", correlation_id=uuid.uuid4(),
        )

        result = check_action_before_execution(
            db_session, redis_client, case_id=case.id,
            proposed_action=RecoveryAction.RETRY, correlation_id=uuid.uuid4(),
            risk_score=0.1,
        )
        expected_retry_counts_seen.append(result.policy_decision.context_snapshot["retry_count"])

        assert result.approved is True, f"attempt {attempt_number} should have been allowed"
        assert case.current_state is CaseState.ACTION_PENDING

        _execute_and_fail_one_retry_attempt(sm, case.id)
        assert case.current_state is CaseState.FAILED

        sm.transition(
            case.id, to_state=CaseState.DECISION, reason="attempting recovery again",
            actor="system:recovery", correlation_id=uuid.uuid4(),
        )

    assert expected_retry_counts_seen == [0, 1, 2]

    assert case.current_state is CaseState.DECISION
    sm.transition(
        case.id, to_state=CaseState.ACTION_PENDING, reason="RETRY proposed again",
        actor="agent:llm", correlation_id=uuid.uuid4(),
    )

    result = check_action_before_execution(
        db_session, redis_client, case_id=case.id,
        proposed_action=RecoveryAction.RETRY, correlation_id=uuid.uuid4(),
        risk_score=0.1,
    )

    assert result.approved is False
    assert result.policy_decision.verdict_type is PolicyVerdictType.FORCE_ACTION
    assert result.policy_decision.rule_id == "max_retry_count_exceeded"
    assert result.policy_decision.context_snapshot["retry_count"] == 3
    assert case.current_state is CaseState.STOPPED

    executed_retry_transitions = [
        t for t in sm.history(case.id)
        if t.to_state is CaseState.ACTION_EXECUTED and t.evidence.get("action") == "RETRY"
    ]
    assert len(executed_retry_transitions) == 3


def test_suspicious_velocity_stops_a_case_mid_loop_before_retry_count_would(
    db_session, redis_client
):
    ensure_default_global_config(db_session)
    sm = RecoveryStateMachine(db_session)
    customer_id = "cust_loop_suspicious"

    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE,
        merchant_id="merchant_1", customer_id=customer_id, payment_id="pay_2",
        order_id="order_2", amount=Decimal("1000.00"), currency="INR",
        payment_method="upi", failure_code="bank_timeout", failure_reason="payment_failed",
        reason="payment.failed webhook received", actor="system:ingestion",
    )
    for to_state in [
        CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION, CaseState.ACTION_PENDING,
    ]:
        sm.transition(
            case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
            correlation_id=uuid.uuid4(),
        )

    result_1 = check_action_before_execution(
        db_session, redis_client, case_id=case.id,
        proposed_action=RecoveryAction.RETRY, correlation_id=uuid.uuid4(),
        risk_score=0.1,
    )
    assert result_1.approved is True

    _execute_and_fail_one_retry_attempt(sm, case.id)

    for _ in range(5):
        record_action_attempt(
            redis_client, case_id=uuid.uuid4(), customer_id=customer_id,
            cooldown_seconds=1, velocity_window_seconds=600,
        )

    sm.transition(
        case.id, to_state=CaseState.DECISION, reason="attempting recovery again",
        actor="system:recovery", correlation_id=uuid.uuid4(),
    )
    sm.transition(
        case.id, to_state=CaseState.ACTION_PENDING, reason="RETRY proposed again",
        actor="agent:llm", correlation_id=uuid.uuid4(),
    )

    result_2 = check_action_before_execution(
        db_session, redis_client, case_id=case.id,
        proposed_action=RecoveryAction.RETRY, correlation_id=uuid.uuid4(),
        risk_score=0.1,
    )

    assert result_2.approved is False
    assert result_2.policy_decision.rule_id == "suspicious_velocity_stop_and_escalate"
    assert result_2.policy_decision.requires_escalation is True
    assert result_2.policy_decision.context_snapshot["retry_count"] == 1
    assert case.current_state is CaseState.STOPPED
