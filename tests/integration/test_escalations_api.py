
import base64
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.api.deps import get_db, get_redis
from apps.api.main import app
from models.agent_decision import AgentDecision
from models.enums import CaseState, CaseType, EventType, ProcessingStatus, RecoveryAction
from models.payment_event import PaymentEvent
from models.raw_webhook_event import RawWebhookEvent
from services.accounts.repository import ensure_default_accounts
from services.agent.schema import SCHEMA_VERSION
from services.payments.simulation_provider import SimulationProvider
from services.payments.verification import run_verification
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine

DASHBOARD_CREDENTIALS = "demo_viewer:viewer_pw:viewer,demo_reviewer:reviewer_pw:reviewer"


@pytest.fixture()
def client(db_session, redis_client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_CREDENTIALS", DASHBOARD_CREDENTIALS)
    ensure_default_accounts(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    yield TestClient(app)
    app.dependency_overrides.clear()


def basic_auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


VIEWER_AUTH = basic_auth_header("demo_viewer", "viewer_pw")
REVIEWER_AUTH = basic_auth_header("demo_reviewer", "reviewer_pw")


def make_escalated_case(session, *, payment_id="pay_esc_1"):
    ensure_default_global_config(session)
    ensure_default_recovery_config(session)
    sm = RecoveryStateMachine(session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type=CaseType.PAYMENT_FAILURE, merchant_id="merchant_api_esc",
        customer_id="cust_1", payment_id=payment_id, order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    session.add(AgentDecision(
        case_id=case.id, correlation_id=uuid.uuid4(), proposed_action=RecoveryAction.RETRY,
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
        case.id, to_state=CaseState.ACTION_EXECUTED, reason="RETRY executed (simulated)",
        actor="system:simulated_action_executor", correlation_id=uuid.uuid4(),
        evidence={"action": RecoveryAction.RETRY.value, "simulated": True},
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
        amount=Decimal("500.00"), currency="INR", payment_method="upi",
        timestamp=datetime.now(timezone.utc), raw_payload_reference=raw.id,
        received_at=datetime.now(timezone.utc), processing_status=ProcessingStatus.PROCESSED,
    ))
    session.flush()
    run_verification(session, SimulationProvider(session), case_id=case.id, correlation_id=uuid.uuid4())
    session.refresh(case)
    assert case.current_state is CaseState.ESCALATED
    return case


def test_list_escalations_requires_auth(client):
    response = client.get("/escalations")
    assert response.status_code == 401


def test_list_escalations_with_valid_viewer_auth(client, db_session):
    case = make_escalated_case(db_session)
    response = client.get("/escalations", headers=VIEWER_AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["escalations"][0]["case_id"] == str(case.id)


def test_wrong_password_is_rejected(client, db_session):
    make_escalated_case(db_session)
    response = client.get("/escalations", headers=basic_auth_header("demo_viewer", "wrong"))
    assert response.status_code == 401


def test_viewer_cannot_review(client, db_session):
    case = make_escalated_case(db_session)
    response = client.post(
        f"/escalations/{case.id}/review", headers=VIEWER_AUTH,
        json={"decision": "REJECT", "reason": "viewer trying to act"},
    )
    assert response.status_code == 403


def test_reviewer_can_reject(client, db_session):
    case = make_escalated_case(db_session)
    response = client.post(
        f"/escalations/{case.id}/review", headers=REVIEWER_AUTH,
        json={"decision": "REJECT", "reason": "confirmed fraudulent"},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "REJECT"

    db_session.refresh(case)
    assert case.current_state == CaseState.STOPPED


def test_reviewer_can_approve_and_it_reexecutes(client, db_session):
    case = make_escalated_case(db_session, payment_id="pay_esc_approve")
    response = client.post(
        f"/escalations/{case.id}/review", headers=REVIEWER_AUTH,
        json={"decision": "APPROVE", "reason": "confirmed legitimate"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["final_action"] == "RETRY"
    assert body["gate_approved"] is True


def test_escalation_detail_includes_prior_agent_trace(client, db_session):
    case = make_escalated_case(db_session, payment_id="pay_esc_detail")
    response = client.get(f"/escalations/{case.id}", headers=VIEWER_AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == str(case.id)
    assert len(body["agent_trace"]) == 1
    assert body["agent_trace"][0]["proposed_action"] == "RETRY"
