"""Password hashing and JWT helpers."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

#: bcrypt silently ignores everything past 72 bytes. Rejecting longer input is
#: safer than truncating it, because two different long passwords would otherwise
#: authenticate the same account.
MAX_PASSWORD_BYTES = 72

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class PasswordPolicyError(ValueError):
    """Raised when a password cannot be hashed safely."""


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes long."
        )
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    if len(plain_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return False
    try:
        return pwd_context.verify(plain_password, password_hash)
    except ValueError:
        # A malformed stored hash must not turn into a 500 or an authentication.
        return False


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire, "iat": now}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT. Returns None for anything invalid or expired."""
    if not token or not token.strip():
        return None
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError:
        return None
