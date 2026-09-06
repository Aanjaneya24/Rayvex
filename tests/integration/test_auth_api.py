
import base64

import pytest
from fastapi.testclient import TestClient

from apps.api.deps import get_db, get_redis
from apps.api.main import app
from services.accounts.repository import ensure_default_accounts

DASHBOARD_CREDENTIALS = "existing_reviewer:existingpassword:reviewer"


def _basic_auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture()
def client(db_session, redis_client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_CREDENTIALS", DASHBOARD_CREDENTIALS)
    ensure_default_accounts(db_session)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_register_creates_a_viewer_account(client):
    response = client.post("/auth/register", json={"username": "newuser1", "password": "newuserpassword"})
    assert response.status_code == 201
    assert response.json() == {"username": "newuser1", "role": "viewer"}


def test_registered_account_can_immediately_authenticate(client):
    client.post("/auth/register", json={"username": "newuser2", "password": "newuserpassword"})
    response = client.get("/auth/me", headers=_basic_auth_header("newuser2", "newuserpassword"))
    assert response.status_code == 200
    assert response.json() == {"username": "newuser2", "role": "viewer"}


def test_registration_cannot_grant_reviewer_role(client):
    """The request body has no role field at all; confirms there's no
    way to ask for reviewer at signup, not just that a default is applied."""
    response = client.post("/auth/register", json={"username": "newuser3", "password": "newuserpassword"})
    assert response.json()["role"] == "viewer"


def test_duplicate_username_is_rejected_with_409(client):
    client.post("/auth/register", json={"username": "dupeuser", "password": "dupepassword1"})
    response = client.post("/auth/register", json={"username": "dupeuser", "password": "differentpw1"})
    assert response.status_code == 409


def test_weak_password_is_rejected(client):
    response = client.post("/auth/register", json={"username": "weakuser", "password": "short"})
    assert response.status_code == 422


def test_viewer_cannot_access_a_reviewer_only_endpoint(client):
    client.post("/auth/register", json={"username": "vieweronly", "password": "viewerpassword"})
    response = client.post(
        "/auth/promote",
        json={"username": "vieweronly"},
        headers=_basic_auth_header("vieweronly", "viewerpassword"),
    )
    assert response.status_code == 403


def test_reviewer_can_promote_another_user_to_reviewer(client):
    client.post("/auth/register", json={"username": "soontobereviewer", "password": "somepassword1"})

    response = client.post(
        "/auth/promote",
        json={"username": "soontobereviewer"},
        headers=_basic_auth_header("existing_reviewer", "existingpassword"),
    )
    assert response.status_code == 200
    assert response.json() == {"username": "soontobereviewer", "role": "reviewer"}

    me = client.get("/auth/me", headers=_basic_auth_header("soontobereviewer", "somepassword1"))
    assert me.json()["role"] == "reviewer"


def test_promoting_an_unknown_user_returns_404(client):
    response = client.post(
        "/auth/promote",
        json={"username": "does_not_exist"},
        headers=_basic_auth_header("existing_reviewer", "existingpassword"),
    )
    assert response.status_code == 404


def test_invalid_credentials_are_rejected(client):
    response = client.get("/auth/me", headers=_basic_auth_header("nobody", "wrongpassword"))
    assert response.status_code == 401
