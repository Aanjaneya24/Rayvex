
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from models.enums import CaseState, VerificationOutcome
from services.payments.reconciliation import reconcile_and_reverify
from services.payments.simulation_provider import SimulationProvider
from services.recovery.state_machine import RecoveryStateMachine
from tests.integration.test_payment_verification_flow import (
    drive_case_to_verification_pending,
    insert_payment_event,
)
from models.enums import EventType


def test_failed_case_reconciles_to_recovered_when_captured_event_arrives_later(db_session):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)

    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_FAILED)
    from services.payments.verification import run_verification

    first_result = run_verification(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
    )
    assert first_result.outcome is VerificationOutcome.FAILED
    assert case.current_state is CaseState.FAILED

    history_before_reconciliation = sm.history(case.id)
    transition_count_before = len(history_before_reconciliation)

    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_CAPTURED)

    reconciliation_result = reconcile_and_reverify(
        db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
        reason="late payment.captured event received for this payment_id",
    )

    assert reconciliation_result.outcome is VerificationOutcome.RECOVERED
    assert case.current_state is CaseState.RECOVERED

    full_history = sm.history(case.id)
    assert len(full_history) == transition_count_before + 2
    assert full_history[:transition_count_before] == history_before_reconciliation

    states_in_order = [t.to_state for t in full_history]
    assert CaseState.FAILED in states_in_order
    assert states_in_order.count(CaseState.VERIFICATION_PENDING) == 2
    assert states_in_order[-1] is CaseState.RECOVERED

    original_failed_transition = next(t for t in full_history if t.to_state is CaseState.FAILED)
    assert "verified unsuccessful" in original_failed_transition.reason.lower()


def test_reconciliation_still_independently_reverifies_not_just_trusts_the_new_event(db_session):
    from tests.integration.test_payment_verification_flow import BrokenProvider

    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)
    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_FAILED)
    from services.payments.verification import run_verification

    run_verification(db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4())
    assert case.current_state is CaseState.FAILED

    insert_payment_event(db_session, case, event_type=EventType.PAYMENT_CAPTURED)

    result = reconcile_and_reverify(
        db_session, BrokenProvider(), case_id=case.id, correlation_id=uuid.uuid4(),
        reason="late payment.captured event received",
    )

    assert result.outcome is VerificationOutcome.ERROR
    assert case.current_state is CaseState.VERIFICATION_PENDING
    assert case.current_state is not CaseState.RECOVERED


def test_reconciliation_requires_case_to_actually_be_in_failed(db_session):
    from services.recovery.exceptions import WrongCaseStateError
    import pytest

    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_verification_pending(sm)

    with pytest.raises(WrongCaseStateError):
        reconcile_and_reverify(
            db_session, SimulationProvider(db_session), case_id=case.id, correlation_id=uuid.uuid4(),
            reason="attempted reconciliation on a non-failed case",
        )
