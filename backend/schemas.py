from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Auth ───────────────────────────────────────────────
class UserCreate(BaseModel):
    email: str = Field(..., min_length=5)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


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

    class Config:
        from_attributes = True


class DatasetListResponse(BaseModel):
    datasets: List[DatasetResponse]
    total: int


# ─── Query ──────────────────────────────────────────────
class NLQueryRequest(BaseModel):
    question: str = Field(..., min_length=3)
    dataset_id: str


class ValidationInfo(BaseModel):
    valid: bool
    issues: List[str] = []


class AIQuality(BaseModel):
    intent_detected: bool = True
    sql_validated: bool = True
    chart_selected_correctly: bool = True
    summary_generated: bool = True
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
    generated_sql: Optional[str] = None
    chart_type: Optional[str] = None
    row_count: Optional[int] = None
    is_successful: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Insights ───────────────────────────────────────────
class InsightResponse(BaseModel):
    executive_summary: List[str]
    recommendations: List[str]
    risks: List[str]
    follow_up_questions: List[str]
