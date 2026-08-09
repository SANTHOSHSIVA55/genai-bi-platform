"""Authentication and authorization utilities.

Real JWT-based authentication with:
  - bearer token extraction and signature verification
  - expiration validation
  - subject validation and user lookup
  - inactive-user rejection
  - role-based authorization (admin)
  - refresh token issuing/revocation
  - password reset / email verification token helpers
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
from models import RefreshToken, User

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("app.auth")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "60"))
EMAIL_VERIFY_EXPIRE_HOURS = int(os.getenv("EMAIL_VERIFY_EXPIRE_HOURS", "24"))

_EPHEMERAL_SECRET_WARNING_ISSUED = False


def _as_aware(dt):
    """Normalize a DB-stored datetime to UTC-aware (SQLite returns naive)."""
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_secret_key() -> str:
    """Return the JWT signing secret.

    In production this MUST be set via the SECRET_KEY environment variable.
    If it is not configured, an ephemeral key is generated so that the
    application can still run locally, and a warning is logged. Ephemeral
    keys invalidate issued tokens on process restart.
    """
    global _EPHEMERAL_SECRET_WARNING_ISSUED
    secret = os.getenv("SECRET_KEY")
    if secret and secret.strip():
        return secret.strip()
    if not _EPHEMERAL_SECRET_WARNING_ISSUED:
        logger.warning(
            "SECRET_KEY environment variable is not set. Using an ephemeral "
            "signing key; tokens will be invalidated on restart. Set SECRET_KEY "
            "in production."
        )
        _EPHEMERAL_SECRET_WARNING_ISSUED = True
    return secrets.token_urlsafe(48)


SECRET_KEY = get_secret_key()

security = HTTPBearer(auto_error=False)


# ──────────────────────────────────────────────
#  Password hashing
# ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ──────────────────────────────────────────────
#  Access tokens (JWT)
# ──────────────────────────────────────────────

def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": user.id,
        "role": user.role,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises 401 on any invalid/expired token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def _credentials_user(credentials: HTTPAuthorizationCredentials) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency that authenticates the bearer token and loads the user."""
    payload = _credentials_user(credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == sub).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency that requires an authenticated admin user."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


# ──────────────────────────────────────────────
#  Refresh tokens
# ──────────────────────────────────────────────

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def create_refresh_token(
    user: User, db: Session, ip_address: Optional[str] = None, user_agent: Optional[str] = None
) -> RefreshToken:
    token = _generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    record = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    record.plain_token = token  # ephemeral attribute, never persisted
    return record


def validate_refresh_token(raw_token: str, db: Session) -> RefreshToken:
    """Validate an opaque refresh token, returning its DB record."""
    if not raw_token:
        raise HTTPException(status_code=401, detail="Refresh token required")
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == _hash_token(raw_token))
        .first()
    )
    if not record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if record.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    if _as_aware(record.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired")
    return record


def revoke_refresh_token(record: RefreshToken, db: Session) -> None:
    record.revoked_at = datetime.now(timezone.utc)
    db.commit()


def revoke_all_user_refresh_tokens(user_id: str, db: Session) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()


# ──────────────────────────────────────────────
#  One-time tokens (email verification / password reset)
# ──────────────────────────────────────────────

def create_email_verification_token(user: User, db: Session) -> str:
    from models import EmailVerification

    token = _generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=EMAIL_VERIFY_EXPIRE_HOURS)
    db.add(
        EmailVerification(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=expires_at,
        )
    )
    db.commit()
    return token


def create_password_reset_token(user: User, db: Session) -> str:
    from models import PasswordResetToken

    token = _generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(token),
            expires_at=expires_at,
        )
    )
    db.commit()
    return token


def consume_password_reset_token(raw_token: str, db: Session) -> User:
    from models import PasswordResetToken

    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == _hash_token(raw_token))
        .first()
    )
    if not record or record.used_at is not None or _as_aware(record.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    record.used_at = datetime.now(timezone.utc)
    db.commit()
    return user


def consume_email_verification_token(raw_token: str, db: Session) -> User:
    from models import EmailVerification

    record = (
        db.query(EmailVerification)
        .filter(EmailVerification.token_hash == _hash_token(raw_token))
        .first()
    )
    if not record or record.verified_at is not None or _as_aware(record.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    record.verified_at = datetime.now(timezone.utc)
    user.is_email_verified = True
    db.commit()
    return user
