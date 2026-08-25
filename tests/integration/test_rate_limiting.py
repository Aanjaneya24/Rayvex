
import json
import uuid

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from apps.api.deps import get_db, get_redis
from apps.api.main import app
from apps.api.rate_limit import check_rate_limit
from services.ingestion.webhook_processor import compute_signature

WEBHOOK_SECRET = "test_rate_limit_secret"


@pytest.fixture()
def client(db_session, redis_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    yield TestClient(app)
    app.dependency_overrides.clear()


def _payload():
    return {
        "event": "payment.failed", "razorpay_event_id": f"evt_{uuid.uuid4()}",
        "payload": {"payment": {"entity": {
            "id": f"pay_{uuid.uuid4().hex[:8]}", "order_id": f"order_{uuid.uuid4().hex[:8]}",
            "amount": 10000, "currency": "INR", "method": "upi", "error_code": "bank_timeout",
            "error_description": "timeout", "notes": {"rayvex_merchant_id": "merchant_1", "rayvex_customer_id": "cust_rl"},
        }}},
    }


def _post_signed(client):
    payload = _payload()
    body = json.dumps(payload).encode()
    sig = compute_signature(body, WEBHOOK_SECRET)
    return client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})


def test_requests_under_the_limit_all_succeed(client):
    for _ in range(5):
        response = _post_signed(client)
        assert response.status_code == 200


def test_exceeding_the_limit_returns_429(client, redis_client, monkeypatch):
    import apps.api.rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module, "_MAX_REQUESTS_PER_WINDOW", 3)

    statuses = [_post_signed(client).status_code for _ in range(5)]

    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses[3:]


def test_check_rate_limit_raises_directly_once_exceeded(redis_client):
    class FakeClient:
        host = "10.0.0.1"

    request = Request(scope={
        "type": "http", "headers": [], "client": ("10.0.0.1", 1234),
    })

    for _ in range(2):
        check_rate_limit(redis_client, request, window_seconds=60, max_requests=2)

    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(redis_client, request, window_seconds=60, max_requests=2)
    assert exc_info.value.status_code == 429


def test_different_ips_have_independent_limits(redis_client):
    request_a = Request(scope={"type": "http", "headers": [], "client": ("1.1.1.1", 1234)})
    request_b = Request(scope={"type": "http", "headers": [], "client": ("2.2.2.2", 1234)})

    for _ in range(2):
        check_rate_limit(redis_client, request_a, window_seconds=60, max_requests=2)

    check_rate_limit(redis_client, request_b, window_seconds=60, max_requests=2)
