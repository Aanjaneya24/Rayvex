
import inspect
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from models.enums import CaseState, EventType, ProcessingStatus
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.agent.tools import build_agent_tools
from services.recovery.state_machine import RecoveryStateMachine
from tests.agent.helpers import drive_case_to_action_pending


def test_verify_payment_tool_has_no_session_or_redis_parameter():
    from services.agent.tools.read_tools import build_read_tools
    from services.payments.simulation_provider import SimulationProvider

    source = inspect.getsource(build_read_tools)
    def_line = next(line for line in source.splitlines() if "def verify_payment(" in line)
    assert def_line.strip() == "def verify_payment(payment_id: str) -> dict:"


def test_verify_payment_tool_reflects_real_persisted_data_mode_labeled(db_session, redis_client):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=Decimal("500.00"))

    raw = RawWebhookEvent(
        correlation_id=uuid.uuid4(), razorpay_event_id=f"evt_{uuid.uuid4()}",
        event_type="payment.captured", raw_payload={}, signature_valid=True,
        processing_status=ProcessingStatus.PROCESSED,
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(PaymentEvent(
        event_id=raw.razorpay_event_id, correlation_id=uuid.uuid4(), case_id=case.id,
        payment_id=case.payment_id, order_id=case.order_id, event_type=EventType.PAYMENT_CAPTURED,
        amount=case.amount, currency="INR", payment_method="upi",
        timestamp=datetime.now(timezone.utc), raw_payload_reference=raw.id,
        received_at=datetime.now(timezone.utc), processing_status=ProcessingStatus.PROCESSED,
    ))
    db_session.flush()

    tools = build_agent_tools(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        model_backend="test", model_name="test", prompt_version="v1", schema_version="v1",
        tool_trace=[],
    )
    verify_payment = next(t for t in tools if t.name == "verify_payment")
    result = verify_payment.invoke({"payment_id": case.payment_id})

    assert result["mode"] == "SIMULATION_MODE"
    assert result["status"] == "captured"
    assert "does not mark anything as recovered" in result["note"]


def test_calling_verify_payment_tool_does_not_transition_the_case(db_session, redis_client):
    sm = RecoveryStateMachine(db_session)
    case = drive_case_to_action_pending(sm, failure_code="bank_timeout", amount=Decimal("500.00"))
    state_before = case.current_state
    history_len_before = len(sm.history(case.id))

    tools = build_agent_tools(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(),
        model_backend="test", model_name="test", prompt_version="v1", schema_version="v1",
        tool_trace=[],
    )
    verify_payment = next(t for t in tools if t.name == "verify_payment")
    verify_payment.invoke({"payment_id": case.payment_id})

    assert case.current_state is state_before
    assert case.current_state is CaseState.ACTION_PENDING
    assert len(sm.history(case.id)) == history_len_before
