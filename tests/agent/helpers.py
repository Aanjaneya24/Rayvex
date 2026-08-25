import uuid
from decimal import Decimal

from langchain_core.messages import AIMessage

from models.enums import CaseState, CaseType
from services.recovery.state_machine import RecoveryStateMachine
from tests.agent.fakes import FakeToolCallingChatModel


def drive_case_to_action_pending(sm: RecoveryStateMachine, *, failure_code: str, amount: Decimal, customer_id="cust_1", merchant_id="merchant_1"):
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE,
        merchant_id=merchant_id, customer_id=customer_id, payment_id="pay_1",
        order_id="order_1", amount=amount, currency="INR", payment_method="card",
        failure_code=failure_code, failure_reason="payment_failed",
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
    return case


def record_decision_call(decision_json: str, call_id: str = "call_1") -> AIMessage:
    return AIMessage(
        content="", tool_calls=[
            {"name": "record_decision", "args": {"decision_json": decision_json}, "id": call_id}
        ],
    )


def fake_model_with_responses(*responses: AIMessage) -> FakeToolCallingChatModel:
    return FakeToolCallingChatModel(responses=list(responses))
