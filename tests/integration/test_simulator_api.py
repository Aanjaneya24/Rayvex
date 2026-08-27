
import base64

import pytest
from fastapi.testclient import TestClient

from apps.api.deps import get_db, get_redis
from apps.api.main import app
from models.benchmark_run import BenchmarkRun
from services.accounts.repository import ensure_default_accounts
from services.policy.config_repository import ensure_default_global_config
from services.recovery.recovery_config_repository import ensure_default_recovery_config

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


def test_preview_requires_at_least_one_override(client, db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    response = client.post("/simulator/preview", json={"case_count": 100, "seed": 1})
    assert response.status_code == 400


def test_preview_rejects_disallowed_case_count(client, db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    response = client.post("/simulator/preview", json={"case_count": 42, "seed": 1, "max_retry_count": 5})
    assert response.status_code == 400


def test_preview_returns_baseline_and_draft_with_real_numbers(client, db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    response = client.post(
        "/simulator/preview", json={"case_count": 100, "seed": 7, "max_retry_count": 1},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["changed_fields"] == ["max_retry_count"]
    assert "intelligent_recovery" in body["baseline"]
    assert "intelligent_recovery" in body["draft"]
    assert body["baseline"]["intelligent_recovery"]["revenue_at_risk"] > 0


def test_preview_never_persists_a_benchmark_run(client, db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    before = db_session.query(BenchmarkRun).count()
    client.post("/simulator/preview", json={"case_count": 100, "seed": 3, "cooldown_seconds": 999})
    after = db_session.query(BenchmarkRun).count()

    assert after == before


def test_preview_with_a_tighter_retry_limit_reduces_or_matches_retry_driven_cost(client, db_session):
    ensure_default_global_config(db_session)
    ensure_default_recovery_config(db_session)

    response = client.post(
        "/simulator/preview", json={"case_count": 500, "seed": 11, "max_retry_count": 1},
    )
    body = response.json()

    draft_actions = body["draft"]["intelligent_recovery"]["total_actions_taken"]
    baseline_actions = body["baseline"]["intelligent_recovery"]["total_actions_taken"]
    assert draft_actions <= baseline_actions
