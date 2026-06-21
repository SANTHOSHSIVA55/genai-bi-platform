import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user", nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    datasets = relationship("Dataset", back_populates="owner")
    queries = relationship("QueryLog", back_populates="user")


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
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="datasets")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    dataset_id = Column(String(36), nullable=True)
    dataset_name = Column(String(255), nullable=True)
    question = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    chart_type = Column(String(50), nullable=True)
    row_count = Column(Integer, nullable=True)
    is_successful = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="queries")
