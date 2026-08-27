
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth import AuthenticatedUser, get_current_user, require_reviewer
from apps.api.deps import get_db, get_redis
from apps.api.rate_limit import check_rate_limit
from services.accounts.passwords import WeakPasswordError
from services.accounts.repository import UserNotFoundError, UsernameTakenError, create_user, promote_to_reviewer

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str


class PromoteRequest(BaseModel):
    username: str


@router.post("/register", status_code=201)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db), redis_client=Depends(get_redis)):
    # A new account can only ever be a viewer — the reviewer role, which
    # can approve/reject/override real escalation decisions, is granted
    # separately via /auth/promote by an existing reviewer, never at signup.
    check_rate_limit(redis_client, request, window_seconds=3600, max_requests=20)
    try:
        user = create_user(db, username=body.username, password=body.password)
    except UsernameTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WeakPasswordError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"username": user.username, "role": user.role.value}


@router.get("/me")
def me(user: AuthenticatedUser = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}


@router.post("/promote")
def promote(
    body: PromoteRequest,
    db: Session = Depends(get_db),
    _reviewer: AuthenticatedUser = Depends(require_reviewer),
):
    try:
        user = promote_to_reviewer(db, username=body.username)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"username": user.username, "role": user.role.value}
