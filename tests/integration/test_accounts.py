import pytest

from models.enums import UserRole
from services.accounts.repository import (
    UserNotFoundError,
    UsernameTakenError,
    authenticate,
    create_user,
    ensure_default_accounts,
    get_user_by_username,
    promote_to_reviewer,
)


def test_create_user_defaults_to_viewer(db_session):
    user = create_user(db_session, username="alice", password="alicepassword")
    assert user.role is UserRole.VIEWER


def test_duplicate_username_is_rejected(db_session):
    create_user(db_session, username="bob", password="bobpassword1")
    with pytest.raises(UsernameTakenError):
        create_user(db_session, username="bob", password="differentpassword")


def test_authenticate_succeeds_with_correct_password(db_session):
    create_user(db_session, username="carol", password="carolpassword")
    user = authenticate(db_session, username="carol", password="carolpassword")
    assert user is not None
    assert user.username == "carol"


def test_authenticate_fails_with_wrong_password(db_session):
    create_user(db_session, username="dave", password="davepassword")
    assert authenticate(db_session, username="dave", password="wrongpassword") is None


def test_authenticate_fails_for_unknown_username(db_session):
    assert authenticate(db_session, username="nobody", password="whatever1") is None


def test_promote_to_reviewer_changes_role(db_session):
    create_user(db_session, username="erin", password="erinpassword")
    promoted = promote_to_reviewer(db_session, username="erin")
    assert promoted.role is UserRole.REVIEWER
    assert get_user_by_username(db_session, "erin").role is UserRole.REVIEWER


def test_promote_unknown_user_raises(db_session):
    with pytest.raises(UserNotFoundError):
        promote_to_reviewer(db_session, username="nobody")


def test_ensure_default_accounts_creates_from_env(db_session, monkeypatch):
    monkeypatch.setenv("DASHBOARD_CREDENTIALS", "frank:frankpassword:viewer,grace:gracepassword:reviewer")
    ensure_default_accounts(db_session)
    frank = get_user_by_username(db_session, "frank")
    grace = get_user_by_username(db_session, "grace")
    assert frank is not None and frank.role is UserRole.VIEWER
    assert grace is not None and grace.role is UserRole.REVIEWER


def test_ensure_default_accounts_is_idempotent_and_never_overwrites(db_session, monkeypatch):
    monkeypatch.setenv("DASHBOARD_CREDENTIALS", "henry:henrypassword:viewer")
    ensure_default_accounts(db_session)
    promote_to_reviewer(db_session, username="henry")  # manually promoted afterward

    ensure_default_accounts(db_session)  # called again, e.g. on a second startup

    henry = get_user_by_username(db_session, "henry")
    assert henry.role is UserRole.REVIEWER  # the manual promotion was not clobbered


def test_ensure_default_accounts_is_a_no_op_when_env_var_is_unset(db_session, monkeypatch):
    monkeypatch.delenv("DASHBOARD_CREDENTIALS", raising=False)
    ensure_default_accounts(db_session)  # must not raise
