
import uuid
from decimal import Decimal

import pytest

from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, CaseType, PolicyVerdictType, RecoveryAction
from models.policy_decision import PolicyDecision
from services.policy.config_repository import ensure_default_global_config
from services.policy.redis_guards import record_action_attempt
from services.recovery.action_gate import check_action_before_execution
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.state_machine import RecoveryStateMachine


def drive_case_to_action_pending(sm: RecoveryStateMachine, *, failure_code: str, amount: Decimal, customer_id="cust_1"):
    correlation_id = uuid.uuid4()
    case = sm.create_case(
        correlation_id=correlation_id,
        case_type=CaseType.PAYMENT_FAILURE,
        merchant_id="merchant_1",
        customer_id=customer_id,
        payment_id="pay_1",
        order_id="order_1",
        amount=amount,
        currency="INR",
        payment_method="upi",
        failure_code=failure_code,
        failure_reason="payment_failed",
        reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    for to_state in [
        CaseState.SCREENING,
        CaseState.DIAGNOSING,
        CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION,
        CaseState.ACTION_PENDING,
    ]:
        sm.transition(
            case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
            correlation_id=correlation_id,
        )
    return case


def test_gate_requires_case_to_be_in_action_pending(db_session, redis_client):
    ensure_default_global_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE,
        merchant_id="merchant_1", amount=Decimal("100.00"), reason="r", actor="a",
    )

    with pytest.raises(WrongCaseStateError):
        check_action_before_execution(
            db_session, redis_client, case_id=case.id,
            proposed_action=RecoveryAction.RETRY, correlation_id=uuid.uuid4(),
            risk_score=0.1,
        )


def test_gate_denies_and_stops_case_for_prohibited_retry_category(db_session, redis_client):
    ensure_default_global_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(
        sm, failure_code="insufficient_funds", amount=Decimal("1000.00")
    )
    correlation_id = uuid.uuid4()

    result = check_action_before_execution(
        db_session, redis_client, case_id=case.id,
        proposed_action=RecoveryAction.RETRY, correlation_id=correlation_id,
        risk_score=0.1,
    )

    assert result.approved is False
    assert result.transition is not None
    assert result.transition.to_state is CaseState.STOPPED
    assert result.transition.from_state is CaseState.ACTION_PENDING
    assert case.current_state is CaseState.STOPPED

    decision = db_session.get(PolicyDecision, result.policy_decision.id)
    assert decision is not None
    assert decision.verdict_type is PolicyVerdictType.DENY
    assert decision.rule_id == "prohibited_retry_failure_code"
    assert decision.case_id == case.id
    assert decision.correlation_id == correlation_id

    persisted_transition = db_session.get(CaseStateTransition, result.transition.id)
    assert persisted_transition.policy_decision_id == decision.id
    assert persisted_transition.evidence["rule_id"] == "prohibited_retry_failure_code"


def test_gate_preserves_requires_escalation_flag_even_though_landing_state_is_stopped(
    db_session, redis_client
):
    ensure_default_global_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(
        sm, failure_code="bank_timeout", amount=Decimal("1000.00"), customer_id="cust_susp"
    )
    correlation_id = uuid.uuid4()

    for _ in range(5):
        record_action_attempt(
            redis_client, case_id=uuid.uuid4(), customer_id="cust_susp",
            cooldown_seconds=300, velocity_window_seconds=600,
        )

    result = check_action_before_execution(
        db_session, redis_client, case_id=case.id,
        proposed_action=RecoveryAction.RETRY, correlation_id=correlation_id,
        risk_score=0.1,
    )

    assert result.approved is False
    assert case.current_state is CaseState.STOPPED
    assert result.policy_decision.rule_id == "suspicious_velocity_stop_and_escalate"
    assert result.policy_decision.requires_escalation is True
    assert result.transition.evidence["requires_escalation"] is True


def test_gate_allows_and_leaves_case_in_action_pending_without_executing_anything(
    db_session, redis_client
):
    ensure_default_global_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(
        sm, failure_code="bank_timeout", amount=Decimal("1000.00")
    )
    correlation_id = uuid.uuid4()

    result = check_action_before_execution(
        db_session, redis_client, case_id=case.id,
        proposed_action=RecoveryAction.RETRY, correlation_id=correlation_id,
        risk_score=0.1,
    )

    assert result.approved is True
    assert result.resulting_action is RecoveryAction.RETRY
    assert result.transition is None
    assert case.current_state is CaseState.ACTION_PENDING

    decision = db_session.get(PolicyDecision, result.policy_decision.id)
    assert decision.verdict_type is PolicyVerdictType.ALLOW

    history = sm.history(case.id)
    assert history[-1].to_state is CaseState.ACTION_PENDING


def test_gate_records_which_policy_config_version_was_active(db_session, redis_client):
    from services.policy.config_repository import DEFAULT_GLOBAL_CONFIG, activate_new_version

    v1 = ensure_default_global_config(db_session)
    v2 = activate_new_version(
        db_session, merchant_id=None, created_by="test",
        **{**DEFAULT_GLOBAL_CONFIG, "max_retry_count": 1},
    )
    assert v2.version == v1.version + 1

    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(
        sm, failure_code="bank_timeout", amount=Decimal("1000.00")
    )

    result = check_action_before_execution(
        db_session, redis_client, case_id=case.id,
        proposed_action=RecoveryAction.RETRY, correlation_id=uuid.uuid4(),
        risk_score=0.1,
    )

    assert result.policy_decision.policy_config_id == v2.id
    assert result.policy_decision.policy_config_version == v2.version
    assert result.policy_decision.policy_config_version != v1.version
