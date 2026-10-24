"""Authentication endpoints: register, login, logout, current user."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.logging_config import get_logger
from app.core.security import (
    PasswordPolicyError,
    create_access_token,
    hash_password,
    verify_password,
)
from app.database.connection import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    try:
        password_hash = hash_password(payload.password)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = User(name=payload.name.strip(), email=email, password_hash=password_hash)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent registrations for the same email: the unique constraint
        # wins and the loser gets the same 409 as the pre-check.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists."
        ) from None
    db.refresh(user)
    logger.info("Registered user %s", user.email)
    return TokenResponse(
        access_token=create_access_token(str(user.id)), user=UserOut.model_validate(user)
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalars(select(User).where(User.email == payload.email.lower())).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        # One message for both cases: do not reveal whether the email exists.
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(
        access_token=create_access_token(str(user.id)), user=UserOut.model_validate(user)
    )


@router.post("/logout")
def logout(_: User = Depends(get_current_user)) -> dict:
    """Stateless JWT logout: the client discards the token."""
    return {"detail": "Logged out. Discard the access token on the client."}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
