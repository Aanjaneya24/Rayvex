
import os
import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

VIEWER_ROLE = "viewer"
REVIEWER_ROLE = "reviewer"
_VALID_ROLES = {VIEWER_ROLE, REVIEWER_ROLE}


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str


class AuthNotConfiguredError(RuntimeError):
    pass


def _load_credentials() -> dict[str, tuple[str, str]]:
    raw = os.environ.get("DASHBOARD_CREDENTIALS", "").strip()
    if not raw:
        raise AuthNotConfiguredError(
            "DASHBOARD_CREDENTIALS is not set. Copy the example in .env.example "
            "and configure real credentials — the dashboard API refuses to run "
            "without explicit auth configuration."
        )
    credentials: dict[str, tuple[str, str]] = {}
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) != 3:
            raise AuthNotConfiguredError(
                f"Malformed DASHBOARD_CREDENTIALS entry {entry!r} — expected "
                f"'username:password:role'."
            )
        username, password, role = parts
        if role not in _VALID_ROLES:
            raise AuthNotConfiguredError(f"Unknown role {role!r} for user {username!r}.")
        credentials[username] = (password, role)
    return credentials


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> AuthenticatedUser:
    try:
        known = _load_credentials()
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    entry = known.get(credentials.username)
    expected_password = entry[0] if entry is not None else "invalid-username-placeholder"
    password_ok = secrets.compare_digest(credentials.password, expected_password)
    if entry is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return AuthenticatedUser(username=credentials.username, role=entry[1])


def require_reviewer(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if user.role != REVIEWER_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires the '{REVIEWER_ROLE}' role; "
                   f"'{user.username}' has '{user.role}'.",
        )
    return user
