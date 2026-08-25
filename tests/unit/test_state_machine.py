
from decimal import Decimal
import uuid

import pytest

from models.case_state_transition import CaseStateTransition
from models.enums import CaseState, CaseType
from services.recovery.exceptions import CaseNotFoundError, InvalidTransitionError
from services.recovery.state_machine import RecoveryStateMachine
from services.recovery.transitions import (
    ALLOWED_TRANSITIONS,
    is_allowed,
    is_reconciliation,
    is_retry_reattempt,
)


def make_case(sm: RecoveryStateMachine, correlation_id=None):
    return sm.create_case(
        correlation_id=correlation_id or uuid.uuid4(),
        case_type=CaseType.PAYMENT_FAILURE,
        merchant_id="merchant_1",
        customer_id="cust_1",
        payment_id="pay_abc123",
        order_id="order_abc123",
        amount=Decimal("4999.00"),
        currency="INR",
        payment_method="upi",
        failure_code="BAD_REQUEST_ERROR",
        failure_reason="payment_failed",
        reason="payment.failed webhook received",
        actor="system:ingestion",
    )


def test_create_case_starts_in_received(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)

    assert case.current_state == CaseState.RECEIVED
    assert case.id is not None


def test_create_case_persists_initiating_transition(db_session):
    sm = RecoveryStateMachine(db_session)
    correlation_id = uuid.uuid4()
    case = make_case(sm, correlation_id=correlation_id)

    rows = db_session.query(CaseStateTransition).filter_by(case_id=case.id).all()
    assert len(rows) == 1
    t = rows[0]
    assert t.from_state is None
    assert t.to_state == CaseState.RECEIVED
    assert t.correlation_id == correlation_id
    assert t.actor == "system:ingestion"
    assert t.reason == "payment.failed webhook received"


def test_valid_transition_updates_case_and_persists_row(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    correlation_id = uuid.uuid4()

    transition = sm.transition(
        case.id,
        to_state=CaseState.SCREENING,
        reason="entering risk screening",
        actor="system:pipeline",
        correlation_id=correlation_id,
        evidence={"velocity_check": "pending"},
    )

    assert case.current_state == CaseState.SCREENING
    assert transition.from_state == CaseState.RECEIVED
    assert transition.to_state == CaseState.SCREENING
    assert transition.correlation_id == correlation_id
    assert transition.evidence == {"velocity_check": "pending"}

    persisted = db_session.get(CaseStateTransition, transition.id)
    assert persisted is not None
    assert persisted.to_state == CaseState.SCREENING


def test_full_happy_path_persists_every_step(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    correlation_id = uuid.uuid4()

    path = [
        CaseState.SCREENING,
        CaseState.DIAGNOSING,
        CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION,
        CaseState.ACTION_PENDING,
        CaseState.ACTION_EXECUTED,
        CaseState.VERIFICATION_PENDING,
        CaseState.RECOVERED,
    ]
    for to_state in path:
        sm.transition(
            case.id,
            to_state=to_state,
            reason=f"advancing to {to_state.value}",
            actor="system:pipeline",
            correlation_id=correlation_id,
        )

    assert case.current_state == CaseState.RECOVERED

    history = sm.history(case.id)
    assert [t.to_state for t in history] == [CaseState.RECEIVED] + path
    assert [t.from_state for t in history] == [None, CaseState.RECEIVED] + path[:-1]


def test_skipping_states_is_rejected(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)

    with pytest.raises(InvalidTransitionError):
        sm.transition(
            case.id,
            to_state=CaseState.DECISION,
            reason="attempted skip",
            actor="agent:llm",
            correlation_id=uuid.uuid4(),
        )

    assert case.current_state == CaseState.RECEIVED
    assert len(sm.history(case.id)) == 1


def test_reversing_a_transition_is_rejected(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    sm.transition(
        case.id,
        to_state=CaseState.SCREENING,
        reason="advance",
        actor="system:pipeline",
        correlation_id=uuid.uuid4(),
    )

    with pytest.raises(InvalidTransitionError):
        sm.transition(
            case.id,
            to_state=CaseState.RECEIVED,
            reason="attempted reversal",
            actor="agent:llm",
            correlation_id=uuid.uuid4(),
        )

    assert case.current_state == CaseState.SCREENING


@pytest.mark.parametrize(
    "terminal_state",
    [CaseState.RECOVERED, CaseState.STOPPED],
)
def test_terminal_states_have_no_outgoing_transitions(db_session, terminal_state):
    assert ALLOWED_TRANSITIONS[terminal_state] == frozenset()


def test_escalated_has_human_review_outgoing_edges():
    assert ALLOWED_TRANSITIONS[CaseState.ESCALATED] == frozenset(
        {CaseState.ACTION_PENDING, CaseState.STOPPED}
    )


@pytest.mark.parametrize("any_state", list(CaseState))
def test_no_transition_reaches_received_except_the_initial_one(any_state):
    assert CaseState.RECEIVED not in ALLOWED_TRANSITIONS[any_state]


@pytest.mark.parametrize(
    "state",
    [
        CaseState.SCREENING,
        CaseState.DIAGNOSING,
        CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION,
    ],
)
def test_pre_action_states_can_stop_or_escalate(state):
    assert CaseState.STOPPED in ALLOWED_TRANSITIONS[state]
    assert CaseState.ESCALATED in ALLOWED_TRANSITIONS[state]


def test_action_pending_can_only_advance_or_stop_never_escalate():
    assert ALLOWED_TRANSITIONS[CaseState.ACTION_PENDING] == frozenset(
        {CaseState.ACTION_EXECUTED, CaseState.STOPPED}
    )


def test_failed_case_reconciles_via_new_verification_pending(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    original_correlation_id = uuid.uuid4()

    for to_state in [
        CaseState.SCREENING,
        CaseState.DIAGNOSING,
        CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION,
        CaseState.ACTION_PENDING,
        CaseState.ACTION_EXECUTED,
        CaseState.VERIFICATION_PENDING,
        CaseState.FAILED,
    ]:
        sm.transition(
            case.id,
            to_state=to_state,
            reason="advancing",
            actor="system:pipeline",
            correlation_id=original_correlation_id,
        )

    assert case.current_state == CaseState.FAILED

    reconciliation_correlation_id = uuid.uuid4()
    assert reconciliation_correlation_id != original_correlation_id

    reconciliation_transition = sm.transition(
        case.id,
        to_state=CaseState.VERIFICATION_PENDING,
        reason="late payment.captured event received for this payment_id",
        actor="system:ingestion",
        correlation_id=reconciliation_correlation_id,
        evidence={"reconciliation": True},
    )
    assert is_reconciliation(CaseState.FAILED, CaseState.VERIFICATION_PENDING)
    assert reconciliation_transition.correlation_id == reconciliation_correlation_id
    assert reconciliation_transition.correlation_id != original_correlation_id

    recovered_transition = sm.transition(
        case.id,
        to_state=CaseState.RECOVERED,
        reason="payment.captured verified against Razorpay",
        actor="system:verification",
        correlation_id=reconciliation_correlation_id,
    )

    assert case.current_state == CaseState.RECOVERED
    assert recovered_transition.from_state == CaseState.VERIFICATION_PENDING

    history = sm.history(case.id)
    correlation_ids_used = {t.correlation_id for t in history}
    assert original_correlation_id in correlation_ids_used
    assert reconciliation_correlation_id in correlation_ids_used


def test_failed_has_exactly_two_outgoing_edges_reconciliation_and_retry_reattempt():
    assert ALLOWED_TRANSITIONS[CaseState.FAILED] == frozenset(
        {CaseState.VERIFICATION_PENDING, CaseState.DECISION}
    )


def test_failed_can_loop_back_to_decision_for_another_attempt(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    correlation_id = uuid.uuid4()
    for to_state in [
        CaseState.SCREENING,
        CaseState.DIAGNOSING,
        CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION,
        CaseState.ACTION_PENDING,
        CaseState.ACTION_EXECUTED,
        CaseState.VERIFICATION_PENDING,
        CaseState.FAILED,
    ]:
        sm.transition(
            case.id, to_state=to_state, reason="advancing", actor="system:pipeline",
            correlation_id=correlation_id,
        )

    assert is_retry_reattempt(CaseState.FAILED, CaseState.DECISION)

    transition = sm.transition(
        case.id, to_state=CaseState.DECISION, reason="attempting recovery again",
        actor="system:recovery", correlation_id=uuid.uuid4(),
    )

    assert transition.from_state is CaseState.FAILED
    assert case.current_state is CaseState.DECISION
    assert CaseState.ACTION_PENDING in ALLOWED_TRANSITIONS[CaseState.DECISION]


def test_failed_retry_reattempt_and_reconciliation_are_distinguishable():
    assert is_retry_reattempt(CaseState.FAILED, CaseState.DECISION) is True
    assert is_reconciliation(CaseState.FAILED, CaseState.DECISION) is False
    assert is_retry_reattempt(CaseState.FAILED, CaseState.VERIFICATION_PENDING) is False
    assert is_reconciliation(CaseState.FAILED, CaseState.VERIFICATION_PENDING) is True


def test_recovered_case_cannot_be_reopened(db_session):
    sm = RecoveryStateMachine(db_session)
    case = make_case(sm)
    correlation_id = uuid.uuid4()
    for to_state in [
        CaseState.SCREENING,
        CaseState.DIAGNOSING,
        CaseState.ELIGIBILITY_CHECK,
        CaseState.DECISION,
        CaseState.ACTION_PENDING,
        CaseState.ACTION_EXECUTED,
        CaseState.VERIFICATION_PENDING,
        CaseState.RECOVERED,
    ]:
        sm.transition(
            case.id,
            to_state=to_state,
            reason="advancing",
            actor="system:pipeline",
            correlation_id=correlation_id,
        )

    with pytest.raises(InvalidTransitionError):
        sm.transition(
            case.id,
            to_state=CaseState.VERIFICATION_PENDING,
            reason="attempted reopen",
            actor="agent:llm",
            correlation_id=uuid.uuid4(),
        )


def test_verification_pending_can_escalate_on_ambiguous_result():
    assert CaseState.ESCALATED in ALLOWED_TRANSITIONS[CaseState.VERIFICATION_PENDING]
    assert CaseState.RECOVERED in ALLOWED_TRANSITIONS[CaseState.VERIFICATION_PENDING]
    assert CaseState.FAILED in ALLOWED_TRANSITIONS[CaseState.VERIFICATION_PENDING]


def test_transition_on_unknown_case_raises(db_session):
    sm = RecoveryStateMachine(db_session)
    with pytest.raises(CaseNotFoundError):
        sm.transition(
            uuid.uuid4(),
            to_state=CaseState.SCREENING,
            reason="n/a",
            actor="system:pipeline",
            correlation_id=uuid.uuid4(),
        )


def test_is_allowed_requires_none_from_state_to_target_received_only():
    assert is_allowed(None, CaseState.RECEIVED) is True
    assert is_allowed(None, CaseState.SCREENING) is False


def test_every_non_terminal_state_has_at_least_one_outgoing_edge():
    for state, targets in ALLOWED_TRANSITIONS.items():
        if state in (CaseState.RECOVERED, CaseState.STOPPED):
            continue
        assert len(targets) > 0, f"{state} has no outgoing edges and is not terminal"
