"""Authentication endpoints: register, login, logout, current user."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.logging_config import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.database.connection import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalars(select(User).where(User.email == payload.email.lower())).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Registered user %s", user.email)
    return TokenResponse(
        access_token=create_access_token(str(user.id)), user=UserOut.model_validate(user)
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalars(select(User).where(User.email == payload.email.lower())).first()
    if user is None or not verify_password(payload.password, user.password_hash):
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
