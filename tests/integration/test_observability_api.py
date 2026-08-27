
import base64
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from apps.api.deps import get_db, get_redis
from apps.api.main import app
from models.enums import RecoveryAction
from services.accounts.repository import ensure_default_accounts
from services.policy.config_repository import ensure_default_global_config
from services.policy.redis_guards import record_action_attempt
from services.recovery.case_orchestrator import ScriptedDecision, run_case_pipeline
from services.recovery.recovery_config_repository import ensure_default_recovery_config
from services.recovery.state_machine import RecoveryStateMachine

DASHBOARD_CREDENTIALS = "test_viewer:test_viewer_pw:viewer"


@pytest.fixture()
def client(db_session, redis_client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_CREDENTIALS", DASHBOARD_CREDENTIALS)
    ensure_default_accounts(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    test_client = TestClient(app)
    token = base64.b64encode(b"test_viewer:test_viewer_pw").decode()
    test_client.headers.update({"Authorization": f"Basic {token}"})
    yield test_client
    app.dependency_overrides.clear()


def make_normal_case(db_session, redis_client, *, payment_id):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    sm = RecoveryStateMachine(db_session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type="PAYMENT_FAILURE", merchant_id="merchant_obs",
        customer_id="cust_obs", payment_id=payment_id, order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    return run_case_pipeline(
        db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(), current_hour=12,
        scripted_decision=ScriptedDecision(
            action=RecoveryAction.RETRY, reason="transient timeout, retry",
            confidence=0.8, expected_recovery_value=500.0, risk_level="LOW",
        ),
    )


def make_skipped_case(db_session, redis_client, *, payment_id, customer_id):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)
    for _ in range(10):
        record_action_attempt(
            redis_client, case_id=uuid.uuid4(), customer_id=customer_id,
            cooldown_seconds=1, velocity_window_seconds=3600,
        )
    sm = RecoveryStateMachine(db_session)
    case = sm.create_case(
        correlation_id=uuid.uuid4(), case_type="PAYMENT_FAILURE", merchant_id="merchant_obs",
        customer_id=customer_id, payment_id=payment_id, order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", payment_method="upi", failure_code="bank_timeout",
        failure_reason="payment_failed", reason="payment.failed webhook received",
        actor="system:ingestion",
    )
    return run_case_pipeline(db_session, redis_client, case_id=case.id, correlation_id=uuid.uuid4(), current_hour=12)


def test_observability_summary_reflects_real_decisions(client, db_session, redis_client):
    make_normal_case(db_session, redis_client, payment_id="pay_obs_1")
    make_skipped_case(db_session, redis_client, payment_id="pay_obs_2", customer_id="cust_obs_skip")

    response = client.get("/observability/summary")
    assert response.status_code == 200
    body = response.json()

    assert body["total_decisions"] == 2
    assert body["deterministic_skips"] == 1
    assert body["deterministic_skip_rate"] == 0.5


def test_case_trace_endpoint_returns_real_tool_trace(client, db_session, redis_client):
    result = make_normal_case(db_session, redis_client, payment_id="pay_obs_3")

    response = client.get(f"/observability/cases/{result.case.id}/trace")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == str(result.case.id)
    assert len(body["decisions"]) == 1
    assert body["decisions"][0]["llm_call_count"] == 0
