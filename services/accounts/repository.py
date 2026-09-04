import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.enums import UserRole
from models.user import User
from services.accounts.passwords import hash_password, verify_password


class UsernameTakenError(ValueError):
    pass


class UserNotFoundError(ValueError):
    pass


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.execute(select(User).where(User.username == username)).scalar_one_or_none()


def create_user(session: Session, *, username: str, password: str, role: UserRole = UserRole.VIEWER) -> User:
    if get_user_by_username(session, username) is not None:
        raise UsernameTakenError(f"Username {username!r} is already registered.")
    user = User(username=username, password_hash=hash_password(password), role=role)
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, *, username: str, password: str) -> User | None:
    user = get_user_by_username(session, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def promote_to_reviewer(session: Session, *, username: str) -> User:
    user = get_user_by_username(session, username)
    if user is None:
        raise UserNotFoundError(f"No user {username!r}.")
    user.role = UserRole.REVIEWER
    session.flush()
    return user


def ensure_default_accounts(session: Session) -> None:
    """Bootstraps account(s) from DASHBOARD_CREDENTIALS
    (`username:password:role,...`), skipping any username that already
    exists. Safe to call on every startup."""
    raw = os.environ.get("DASHBOARD_CREDENTIALS", "").strip()
    if not raw:
        return
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) != 3:
            continue
        username, password, role_str = parts
        try:
            role = UserRole(role_str)
        except ValueError:
            continue
        if get_user_by_username(session, username) is None:
            create_user(session, username=username, password=password, role=role)
