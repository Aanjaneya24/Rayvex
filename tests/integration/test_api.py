
import base64
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from apps.api.deps import get_db, get_redis
from apps.api.main import app
from services.ingestion.webhook_processor import compute_signature
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config

WEBHOOK_SECRET = "test_api_webhook_secret"
DASHBOARD_CREDENTIALS = "test_viewer:test_viewer_pw:viewer,test_reviewer:test_reviewer_pw:reviewer"


def _basic_auth_header(username: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


@pytest.fixture()
def client(db_session, redis_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("DASHBOARD_CREDENTIALS", DASHBOARD_CREDENTIALS)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    test_client = TestClient(app)
    test_client.headers.update({"Authorization": _basic_auth_header("test_viewer", "test_viewer_pw")})
    yield test_client
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_routes_require_auth(client):
    client.headers.pop("Authorization", None)
    for path in ("/cases", "/metrics/summary", "/evaluation/benchmark", "/observability/summary"):
        response = client.get(path)
        assert response.status_code == 401, f"{path} did not require auth"


def test_webhook_endpoint_processes_a_valid_signed_payload(client):
    payload = {
        "event": "payment.failed",
        "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_api_1", "order_id": "order_api_1", "amount": 100000, "currency": "INR",
            "method": "upi", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_1"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)

    response = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["case_id"] is not None


def test_webhook_endpoint_publishes_a_case_processing_message(client, rabbitmq_channel):
    """A real webhook hitting the running API must not just create a Case
    row and stop — it has to hand the case off for asynchronous
    processing, which in this architecture means a message lands on the
    case_processing queue."""
    import json as _json

    from services.ingestion.queue import CASE_PROCESSING_QUEUE

    payload = {
        "event": "payment.failed",
        "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_api_queue", "order_id": "order_api_queue", "amount": 100000, "currency": "INR",
            "method": "upi", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_1"},
        }}},
    }
    body = _json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)

    response = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    assert response.status_code == 200
    case_id = response.json()["case_id"]

    method, _, msg_body = rabbitmq_channel.basic_get(queue=CASE_PROCESSING_QUEUE, auto_ack=True)
    assert method is not None, "no message was published for a processed webhook"
    message = _json.loads(msg_body)
    assert message["case_id"] == case_id
    assert message["reconciliation_needed"] is False


def test_webhook_endpoint_rejects_bad_signature(client):
    payload = {"event": "payment.failed", "razorpay_event_id": "evt_bad", "payload": {"payment": {"entity": {
        "id": "pay_bad", "order_id": "order_bad", "amount": 100, "currency": "INR", "method": "upi",
        "error_code": None, "error_description": None, "notes": {},
    }}}}
    body = json.dumps(payload).encode()

    response = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": "wrong"})

    assert response.status_code == 400


def test_case_list_and_detail_round_trip_through_the_real_api(client, db_session):
    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_api_2", "order_id": "order_api_2", "amount": 200000, "currency": "INR",
            "method": "card", "error_code": "insufficient_funds", "error_description": "no funds",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_2"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    ingest_response = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    case_id = ingest_response.json()["case_id"]

    list_response = client.get("/cases")
    assert list_response.status_code == 200
    assert any(c["case_id"] == case_id for c in list_response.json()["cases"])

    detail_response = client.get(f"/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["case"]["case_id"] == case_id
    assert detail["case"]["failure_code"] == "insufficient_funds"
    assert len(detail["timeline"]) == 1
    assert detail["timeline"][0]["to_state"] == "RECEIVED"


def test_case_list_amount_and_date_range_filters(client, db_session):
    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_api_filter_1", "order_id": "order_api_filter_1", "amount": 300000,
            "currency": "INR", "method": "card", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_filter"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    ingest_response = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    case_id = ingest_response.json()["case_id"]

    included = client.get("/cases", params={"amount_min": "2000", "amount_max": "4000"})
    assert any(c["case_id"] == case_id for c in included.json()["cases"])

    excluded = client.get("/cases", params={"amount_min": "5000", "amount_max": "6000"})
    assert not any(c["case_id"] == case_id for c in excluded.json()["cases"])

    future_only = client.get("/cases", params={"created_from": "2999-01-01T00:00:00Z"})
    assert not any(c["case_id"] == case_id for c in future_only.json()["cases"])

    past_to_now = client.get("/cases", params={"created_from": "2000-01-01T00:00:00Z"})
    assert any(c["case_id"] == case_id for c in past_to_now.json()["cases"])


def test_failure_codes_endpoint_returns_only_real_distinct_values(client, db_session):
    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_api_fc_1", "order_id": "order_api_fc_1", "amount": 100000, "currency": "INR",
            "method": "upi", "error_code": "gateway_degradation", "error_description": "degraded",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_fc"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})

    response = client.get("/cases/failure-codes")
    assert response.status_code == 200
    codes = response.json()["failure_codes"]
    assert "gateway_degradation" in codes
    assert None not in codes
    assert codes == sorted(set(codes))


def test_case_detail_includes_real_alternatives_considered(client, db_session):
    from services.policy.config_repository import ensure_default_global_config
    from services.recovery.recovery_config_repository import ensure_default_recovery_config

    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_api_alt_1", "order_id": "order_api_alt_1", "amount": 150000, "currency": "INR",
            "method": "upi", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_alt"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    ingest_response = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    case_id = ingest_response.json()["case_id"]

    response = client.get(f"/cases/{case_id}")
    assert response.status_code == 200
    alternatives = response.json()["alternatives_considered"]

    assert len(alternatives) == 4
    actions = {a["action"] for a in alternatives}
    assert actions == {"RETRY", "SEND_RECOVERY_REMINDER", "SEND_RECOVERY_LINK", "SUGGEST_ALTERNATIVE_PAYMENT_METHOD"}
    for a in alternatives:
        assert 0.0 <= a["probability"] <= 1.0
        assert "expected_recovery_value" in a
    values = [a["expected_recovery_value"] for a in alternatives]
    assert values == sorted(values, reverse=True)


def test_case_detail_404_for_unknown_case(client):
    response = client.get(f"/cases/{uuid.uuid4()}")
    assert response.status_code == 404


def test_policy_config_get_and_update_round_trip(client, db_session):
    ensure_default_global_config(db_session)

    get_response = client.get("/policy/config")
    assert get_response.status_code == 200
    current = get_response.json()
    assert current["max_retry_count"] == 3

    update_body = {**{k: v for k, v in current.items() if k != "version"}, "max_retry_count": 5}
    put_response = client.put("/policy/config", json=update_body)
    assert put_response.status_code == 200
    updated = put_response.json()
    assert updated["max_retry_count"] == 5
    assert updated["version"] == current["version"] + 1

    reget = client.get("/policy/config")
    assert reget.json()["version"] == updated["version"]


def test_benchmark_run_endpoint_returns_real_computed_numbers(client, db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    response = client.post("/evaluation/benchmark", json={"case_count": 100, "seed": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["case_count"] == 100
    assert data["naive_retry"]["revenue_at_risk"] > 0
    assert "recovery_rate" in data["intelligent_recovery"]

    get_response = client.get(f"/evaluation/benchmark/{data['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == data["id"]


def test_benchmark_rejects_disallowed_case_count(client):
    response = client.post("/evaluation/benchmark", json={"case_count": 42, "seed": 1})
    assert response.status_code == 400


def test_benchmark_progress_unknown_token_returns_no_progress_not_an_error(client):
    response = client.get("/evaluation/benchmark/progress/nonexistent-token")
    assert response.status_code == 200
    body = response.json()
    assert body == {"phase": None, "processed": None, "total": None}


def test_benchmark_progress_is_cleaned_up_after_the_run_completes(client, db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    token = f"test-progress-{uuid.uuid4()}"
    response = client.post("/evaluation/benchmark", json={"case_count": 100, "seed": 3, "run_token": token})
    assert response.status_code == 200

    progress = client.get(f"/evaluation/benchmark/progress/{token}")
    assert progress.json() == {"phase": None, "processed": None, "total": None}


def test_metrics_summary_reflects_real_case_data(client, db_session):
    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_metrics_1", "order_id": "order_metrics_1", "amount": 500000, "currency": "INR",
            "method": "upi", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_metrics"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})

    response = client.get("/metrics/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["cases_processed"] >= 1
    assert float(data["revenue_at_risk"]) >= 5000.0


def test_metrics_summary_trend_is_none_with_no_prior_window_data(client, db_session):
    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_metrics_trend_1", "order_id": "order_metrics_trend_1", "amount": 100000,
            "currency": "INR", "method": "upi", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_trend"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})

    response = client.get("/metrics/summary")
    data = response.json()
    assert data["revenue_at_risk_trend_pct"] is None


def test_metrics_summary_trend_is_real_when_prior_window_data_exists(client, db_session):
    from datetime import datetime, timedelta, timezone

    from models.case import Case

    payload = {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": "pay_metrics_trend_2", "order_id": "order_metrics_trend_2", "amount": 100000,
            "currency": "INR", "method": "upi", "error_code": "bank_timeout", "error_description": "timeout",
            "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_trend_2"},
        }}},
    }
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    ingest_response = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    case_id = ingest_response.json()["case_id"]

    old_case = db_session.get(Case, uuid.UUID(case_id))
    old_case.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
    db_session.flush()

    payload2 = {**payload, "razorpay_event_id": f"evt_{uuid.uuid4()}"}
    payload2["payload"]["payment"]["entity"] = {
        **payload["payload"]["payment"]["entity"],
        "id": "pay_metrics_trend_3", "order_id": "order_metrics_trend_3",
    }
    body2 = json.dumps(payload2).encode()
    sig2 = compute_signature(body2, WEBHOOK_SECRET)
    client.post("/webhooks/razorpay", content=body2, headers={"X-Razorpay-Signature": sig2})

    response = client.get("/metrics/summary")
    data = response.json()
    assert data["revenue_at_risk_trend_pct"] is not None
    assert data["revenue_at_risk_trend_pct"] > 0
