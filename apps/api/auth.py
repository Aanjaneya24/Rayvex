
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from apps.api.deps import get_db
from models.enums import UserRole
from services.accounts.repository import authenticate

security = HTTPBasic()

VIEWER_ROLE = UserRole.VIEWER.value
REVIEWER_ROLE = UserRole.REVIEWER.value


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str


def get_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    user = authenticate(db, username=credentials.username, password=credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return AuthenticatedUser(username=user.username, role=user.role.value)


def require_reviewer(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if user.role != REVIEWER_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This action requires the '{REVIEWER_ROLE}' role; "
                   f"'{user.username}' has '{user.role}'.",
        )
    return user
