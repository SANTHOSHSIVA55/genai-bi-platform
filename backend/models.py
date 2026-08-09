import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Boolean,
    Integer,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database import Base


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    datasets = relationship("Dataset", back_populates="owner", cascade="all, delete-orphan")
    queries = relationship("QueryLog", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)
    table_name = Column(String(255), unique=True, nullable=False)
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    columns_info = Column(Text, nullable=True)
    file_size = Column(Integer, default=0)
    owner_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime, default=_now, nullable=False, index=True)

    owner = relationship("User", back_populates="datasets")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dataset_name = Column(String(255), nullable=True)
    question = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    chart_type = Column(String(50), nullable=True)
    row_count = Column(Integer, nullable=True)
    is_successful = Column(Boolean, default=False, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False, index=True)

    user = relationship("User", back_populates="queries")
    dataset = relationship("Dataset")


class AuthLog(Base):
    __tablename__ = "auth_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, index=True)
    username = Column(String(100), nullable=True, index=True)
    attempt_type = Column(String(50), nullable=False)  # login/register/refresh/logout
    is_successful = Column(Boolean, default=False, nullable=False)
    error_message = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False, index=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)


class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False, index=True)
