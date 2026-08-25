
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from models.agent_decision import AgentDecision
from models.enums import CaseState, CaseType, EventType, HumanReviewDecision, ProcessingStatus, RecoveryAction
from models.human_review_action import HumanReviewAction
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.agent.schema import SCHEMA_VERSION
from services.payments.simulation_provider import SimulationProvider
from services.payments.verification import run_verification
from services.policy.config_repository import ensure_default_global_config
from services.recovery.exceptions import WrongCaseStateError
from services.recovery.human_review import InvalidHumanReviewError, review_escalated_case
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine


def drive_case_to_escalated(
    session, *, proposed_action=RecoveryAction.RETRY, payment_id="pay_1", failure_code="bank_timeout",
):
    ensure_default_global_config(session)
    ensure_default_recovery_config(session)
    sm = RecoveryStateMachine(session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_hr_1",
        customer_id="cust_1", payment_id=payment_id, order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code=failure_code,
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    session.add(AgentDecision(
        case_id=case.id, correlation_id=uuid.uuid4(), proposed_action=proposed_action,
        reason="test decision", confidence=0.8, expected_recovery_value=500.0,
        risk_level="LOW", model_backend="test", model_name="test", prompt_version="v1",
        schema_version=SCHEMA_VERSION, tool_trace=[],
    ))
    session.flush()

    for to_state in [
        CaseState.SCREENING, CaseState.DIAGNOSING, CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION, CaseState.ACTION_PENDING,
    ]:
        sm.transition(case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
                       correlation_id=uuid.uuid4())
    sm.transition(
        case.id, to_state=CaseState.ACTION_EXECUTED, reason=f"{proposed_action.value} executed (simulated)",
        actor="system:simulated_action_executor", correlation_id=uuid.uuid4(),
        evidence={"action": proposed_action.value, "simulated": True},
    )
    sm.transition(case.id, to_state=CaseState.VERIFICATION_PENDING, reason="advancing",
                   actor="system:pipeline", correlation_id=uuid.uuid4())

    raw = RawWebhookEvent(
        correlation_id=uuid.uuid4(), razorpay_event_id=f"evt_{uuid.uuid4()}",
        event_type=EventType.PAYMENT_CAPTURED.value, raw_payload={}, signature_valid=True,
        processing_status=ProcessingStatus.PROCESSED,
    )
    session.add(raw)
    session.flush()
    session.add(PaymentEvent(
        event_id=raw.razorpay_event_id, correlation_id=uuid.uuid4(), case_id=case.id,
        payment_id=case.payment_id, order_id=case.order_id, event_type=EventType.PAYMENT_CAPTURED,
        amount=Decimal("500.00"),
        currency="INR", payment_method="upi", timestamp=datetime.now(timezone.utc),
        raw_payload_reference=raw.id, received_at=datetime.now(timezone.utc),
        processing_status=ProcessingStatus.PROCESSED,
    ))
    session.flush()

    run_verification(session, SimulationProvider(session), case_id=case.id, correlation_id=uuid.uuid4())
    session.refresh(case)
    assert case.current_state is CaseState.ESCALATED
    return case


def test_reject_ends_case_at_stopped_and_is_audited(db_session, redis_client):
    case = drive_case_to_escalated(db_session)

    result = review_escalated_case(
        db_session, redis_client, case_id=case.id, reviewer="ops_alice",
        decision=HumanReviewDecision.REJECT, reason="clearly fraudulent, do not pursue",
    )

    db_session.refresh(case)
    assert case.current_state is CaseState.STOPPED
    assert result.review_action.decision == HumanReviewDecision.REJECT
    assert result.review_action.final_action is None
    assert result.review_action.reviewer == "ops_alice"

    audited = db_session.query(HumanReviewAction).filter_by(case_id=case.id).all()
    assert len(audited) == 1


def test_approve_resumes_and_reexecutes_original_action(db_session, redis_client):
    case = drive_case_to_escalated(db_session, proposed_action=RecoveryAction.RETRY)

    result = review_escalated_case(
        db_session, redis_client, case_id=case.id, reviewer="ops_bob",
        decision=HumanReviewDecision.APPROVE, reason="looks legitimate, proceed with retry",
    )

    assert result.review_action.final_action == RecoveryAction.RETRY
    assert result.gate_result is not None
    assert result.gate_result.approved is True
    assert result.verification_result is not None


def test_approve_is_genuinely_denied_by_the_real_gate_not_a_bypass(db_session, redis_client):
    case = drive_case_to_escalated(
        db_session, proposed_action=RecoveryAction.RETRY, payment_id="pay_hr_denied",
        failure_code="insufficient_funds",
    )

    result = review_escalated_case(
        db_session, redis_client, case_id=case.id, reviewer="ops_zoe",
        decision=HumanReviewDecision.APPROVE, reason="approving retry despite insufficient_funds",
    )

    assert result.gate_result is not None
    assert result.gate_result.approved is False
    assert result.gate_result.policy_decision.rule_id == "prohibited_retry_failure_code"
    assert result.verification_result is None

    db_session.refresh(case)
    assert case.current_state is CaseState.STOPPED


def test_approve_with_no_prior_proposal_requires_explicit_action(db_session, redis_client):
    sm = RecoveryStateMachine(db_session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_hr_2",
        customer_id="cust_1", payment_id="pay_no_proposal", order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    for to_state in [CaseState.SCREENING, CaseState.ESCALATED]:
        sm.transition(case.id, to_state=to_state, reason="escalating pre-action", actor="system:pipeline",
                       correlation_id=uuid.uuid4())

    with pytest.raises(InvalidHumanReviewError):
        review_escalated_case(
            db_session, redis_client, case_id=case.id, reviewer="ops_carol",
            decision=HumanReviewDecision.APPROVE, reason="approve without an action",
        )


def test_override_authorizes_a_different_action(db_session, redis_client):
    case = drive_case_to_escalated(db_session, proposed_action=RecoveryAction.RETRY, payment_id="pay_override")

    result = review_escalated_case(
        db_session, redis_client, case_id=case.id, reviewer="ops_dave",
        decision=HumanReviewDecision.OVERRIDE, reason="retry is wrong here, send a reminder instead",
        action=RecoveryAction.SEND_RECOVERY_REMINDER,
    )

    assert result.review_action.original_proposed_action == RecoveryAction.RETRY
    assert result.review_action.final_action == RecoveryAction.SEND_RECOVERY_REMINDER


def test_override_without_action_is_rejected(db_session, redis_client):
    case = drive_case_to_escalated(db_session, payment_id="pay_override_2")

    with pytest.raises(InvalidHumanReviewError):
        review_escalated_case(
            db_session, redis_client, case_id=case.id, reviewer="ops_erin",
            decision=HumanReviewDecision.OVERRIDE, reason="missing action",
        )


def test_cannot_review_a_case_not_in_escalated(db_session, redis_client):
    sm = RecoveryStateMachine(db_session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_hr_3",
        customer_id="cust_1", payment_id="pay_not_escalated", order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )

    with pytest.raises(WrongCaseStateError):
        review_escalated_case(
            db_session, redis_client, case_id=case.id, reviewer="ops_frank",
            decision=HumanReviewDecision.REJECT, reason="not escalated",
        )


def test_approve_action_mismatch_with_original_proposal_is_rejected(db_session, redis_client):
    case = drive_case_to_escalated(db_session, proposed_action=RecoveryAction.RETRY, payment_id="pay_mismatch")

    with pytest.raises(InvalidHumanReviewError):
        review_escalated_case(
            db_session, redis_client, case_id=case.id, reviewer="ops_gina",
            decision=HumanReviewDecision.APPROVE, reason="approve a different action than proposed",
            action=RecoveryAction.SEND_RECOVERY_LINK,
        )
