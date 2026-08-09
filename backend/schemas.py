import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

# ─── Validation constants ───────────────────────────────
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,50}$")


# ─── Auth ───────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not USERNAME_PATTERN.match(value):
            raise ValueError(
                "Username may only contain letters, numbers, dots, dashes and underscores (3-50 chars)"
            )
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.islower() for c in value) or not any(c.isupper() for c in value):
            raise ValueError("Password must contain both uppercase and lowercase letters")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one number")
        return value


class UserLogin(BaseModel):
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10, max_length=512)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=512)
    password: str = Field(..., min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=512)


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    is_email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    message: str


# ─── Dataset ────────────────────────────────────────────
class DatasetResponse(BaseModel):
    id: str
    name: str
    original_filename: str
    file_type: str
    table_name: str
    row_count: int
    column_count: int
    columns_info: Optional[str] = None
    file_size: Optional[int] = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetListResponse(BaseModel):
    datasets: List[DatasetResponse]
    total: int
    page: int = 1
    page_size: int = 50


class DatasetPreviewResponse(BaseModel):
    dataset: DatasetResponse
    columns: list
    sample_rows: list


# ─── Query ──────────────────────────────────────────────
class NLQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    dataset_id: str = Field(..., min_length=8, max_length=64, pattern=r"^[0-9a-fA-F-]+$")

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class ValidationInfo(BaseModel):
    valid: bool
    issues: List[str] = []
    suggested_fix: Optional[str] = None


class AIQuality(BaseModel):
    intent_detected: bool = True
    sql_generated: bool = True
    sql_validated: bool = True
    chart_selected_correctly: bool = True
    summary_generated: bool = True
    recommendations_generated: bool = True
    follow_up_generated: bool = True
    sql_executed_successfully: bool = True
    capability_match: bool = True
    visualization_quality: bool = True
    overall_score: float = 100.0
    step_scores: dict = {}
    issues: List[str] = []


class QueryResultResponse(BaseModel):
    question: str
    generated_sql: str
    data: List[dict]
    chart_type: str
    chart_config: dict
    summary: dict
    follow_up_questions: List[str]
    ai_quality: Optional[AIQuality] = None
    validation_info: Optional[ValidationInfo] = None


class QueryLogResponse(BaseModel):
    id: str
    question: str
    dataset_name: Optional[str] = None
    dataset_id: Optional[str] = None
    generated_sql: Optional[str] = None
    chart_type: Optional[str] = None
    row_count: Optional[int] = None
    is_successful: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class QueryLogListResponse(BaseModel):
    queries: List[QueryLogResponse]
    total: int


# ─── Pagination ─────────────────────────────────────────
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=100)


# ─── Admin ──────────────────────────────────────────────
class UserAdminUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = Field(None, pattern=r"^(user|admin)$")


class Insights(BaseModel):
    executive_summary: List[str]
    recommendations: List[str]
    risks: List[str]
    follow_up_questions: List[str]
