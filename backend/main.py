import json
import asyncio
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai import (
    _local_nl_to_sql,
    USE_AI,
    detect_chart_type,
    generate_ai_quality,
    generate_insights,
    nl_to_sql,
    validate_sql_intent,
)
from ai.columns import _parse_columns_info
from ai.clarity import check_question_feasibility
from ai.context import resolve_followup_question
from ai.joins import build_multi_table_sql
from ai.profile import build_profile, detect_currency
from ai.relationships import detect_relationships
from ai.result_check import validate_result
from ai.semantics import analyze_sql_semantics
from ai.sql_validator import validate_sql_intent_multi
from ai.sufficiency import check_sufficiency
from ai.questions import (
    _preferred_metric,
    _preferred_category,
    classify_columns,
    generate_guidance_questions,
    generate_quick_questions,
)
from ai.provider import provider_info
from audit import write_audit
from auth import (
    consume_email_verification_token,
    consume_password_reset_token,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    require_admin,
    revoke_all_user_refresh_tokens,
    revoke_refresh_token,
    validate_refresh_token,
    verify_password,
)
from data_cleaner import assess_data_quality, clean_dataframe, get_column_info, read_uploaded_file
from database import engine, get_db, get_dynamic_table_names, init_db
from logging_config import request_id_var, setup_logging
from models import Dataset, QueryLog, User
from query_cache import build_cache_key, clear_query_cache, get_cached, put_cached
from schemas import (
    DatasetListResponse,
    DatasetPreviewResponse,
    DatasetProfileResponse,
    DatasetQuestionsResponse,
    DatasetResponse,
    DatasetRowsResponse,
    ForgotPasswordRequest,
    MessageResponse,
    NLQueryRequest,
    QueryLogListResponse,
    QueryLogResponse,
    QueryResultResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserAdminUpdate,
    UserCreate,
    UserLogin,
    UserResponse,
    VerifyEmailRequest,
)
from services.email_service import send_password_reset_email, send_verification_email
from sql_validator import validate_sql

load_dotenv()
setup_logging()

logger = logging.getLogger("app.main")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://0.0.0.0:3000",
    "https://genaibi.vercel.app",
]

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {"csv", "tsv", "json", "xlsx", "xls", "pdf"}
PREVIEW_LIMIT = 20
RESULT_LIMIT = 1000


# ──────────────────────────────────────────────
#  Rate limiting
# ──────────────────────────────────────────────

def _rate_limit_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_rate_limit_key, default_limits=[])


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Application started")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title="GenAI BI Platform",
    description="Natural Language Business Intelligence powered by Generative AI",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again later."},
        headers={"Retry-After": str(getattr(exc, "retry_after", ""))},
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("%s %s -> %s (%.1f ms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _client_ua(request: Request) -> Optional[str]:
    return request.headers.get("User-Agent")


def _safe_filename(filename: str) -> str:
    """Strip any path components from an uploaded filename."""
    return os.path.basename(filename.replace("\\", "/"))


def _json_safe(value):
    """Convert a DB value into a JSON-serializable primitive.

    PostgreSQL returns Decimal for aggregate functions (SUM/AVG/ROUND); those are
    converted to float so downstream consumers receive real numbers, not strings.
    """
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _get_owned_dataset(dataset_id: str, current_user: User, db: Session) -> Dataset:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if current_user.role != "admin" and dataset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return dataset


def _drop_table(table_name: str) -> None:
    with engine.connect() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        conn.commit()


def _cleanup_orphan_tables(db: Session) -> None:
    """Drop leftover ds_* tables that no longer correspond to a Dataset row."""
    referenced = {t[0] for t in db.query(Dataset.table_name).all()}
    for table_name in get_dynamic_table_names():
        if table_name not in referenced:
            logger.warning("Dropping orphan table %s", table_name)
            _drop_table(table_name)


# ──────────────────────────────────────────────
#  AUTH ROUTES
# ──────────────────────────────────────────────

@app.post("/api/auth/register", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("10/minute")
def register(request: Request, body: UserCreate, db: Session = Depends(get_db)):
    ip_addr = _client_ip(request)

    if db.query(User).filter(User.email == body.email).first():
        write_audit(db, "register.failed", entity_type="user", entity_id=body.email,
                    details="Email already registered", ip_address=ip_addr)
        raise HTTPException(status_code=400, detail="Email already registered")

    if db.query(User).filter(User.username == body.username).first():
        write_audit(db, "register.failed", entity_type="user", entity_id=body.email,
                    details="Username already taken", ip_address=ip_addr)
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Issue email verification token (non-blocking for the response)
    verification_token = create_email_verification_token(user, db)
    send_verification_email(user.email, verification_token)

    write_audit(db, "register", user_id=user.id, entity_type="user", entity_id=user.id,
                ip_address=ip_addr)

    access_token = create_access_token(user)
    refresh_record = create_refresh_token(user, db, ip_address=ip_addr, user_agent=_client_ua(request))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_record.plain_token,
        expires_in=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")) * 60,
        user=UserResponse.model_validate(user),
    )


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("10/minute")
def login(request: Request, body: UserLogin, db: Session = Depends(get_db)):
    ip_addr = _client_ip(request)
    user = db.query(User).filter(User.email == body.email).first()

    if not user or not verify_password(body.password, user.hashed_password):
        write_audit(db, "login.failed", entity_type="user", entity_id=body.email,
                    details="Invalid credentials", ip_address=ip_addr)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        write_audit(db, "login.failed", user_id=user.id, entity_type="user", entity_id=user.id,
                    details="Account disabled", ip_address=ip_addr)
        raise HTTPException(status_code=403, detail="Account disabled")

    write_audit(db, "login", user_id=user.id, entity_type="user", entity_id=user.id, ip_address=ip_addr)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    access_token = create_access_token(user)
    refresh_record = create_refresh_token(user, db, ip_address=ip_addr, user_agent=_client_ua(request))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_record.plain_token,
        expires_in=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")) * 60,
        user=UserResponse.model_validate(user),
    )


@app.post("/api/auth/refresh", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("30/minute")
def refresh_token(request: Request, body: RefreshRequest, db: Session = Depends(get_db)):
    record = validate_refresh_token(body.refresh_token, db)
    user = db.query(User).filter(User.id == record.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Rotate: revoke the presented token and issue a fresh pair
    revoke_refresh_token(record, db)
    access_token = create_access_token(user)
    new_refresh = create_refresh_token(user, db, ip_address=_client_ip(request), user_agent=_client_ua(request))
    write_audit(db, "token.refresh", user_id=user.id, entity_type="user", entity_id=user.id, ip_address=_client_ip(request))

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh.plain_token,
        expires_in=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")) * 60,
        user=UserResponse.model_validate(user),
    )


@app.post("/api/auth/logout", response_model=MessageResponse, tags=["Auth"])
def logout(
    request: Request,
    body: RefreshRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    revoke_all_user_refresh_tokens(current_user.id, db)
    write_audit(db, "logout", user_id=current_user.id, entity_type="user", entity_id=current_user.id,
                ip_address=_client_ip(request))
    return MessageResponse(message="Logged out")


@app.get("/api/auth/me", response_model=UserResponse, tags=["Auth"])
def get_profile(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@app.post("/api/auth/verify-email", response_model=MessageResponse, tags=["Auth"])
@limiter.limit("10/minute")
def verify_email(request: Request, body: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = consume_email_verification_token(body.token, db)
    write_audit(db, "email.verified", user_id=user.id, entity_type="user", entity_id=user.id,
                ip_address=_client_ip(request))
    return MessageResponse(message="Email verified successfully")


@app.post("/api/auth/forgot-password", response_model=MessageResponse, tags=["Auth"])
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always respond with the same message to avoid user enumeration.
    user = db.query(User).filter(User.email == body.email).first()
    if user and user.is_active:
        token = create_password_reset_token(user, db)
        send_password_reset_email(user.email, token)
        write_audit(db, "password.reset.requested", user_id=user.id, entity_type="user",
                    entity_id=user.id, ip_address=_client_ip(request))
    return MessageResponse(
        message="If an account exists for that email, a password reset link has been sent."
    )


@app.post("/api/auth/reset-password", response_model=MessageResponse, tags=["Auth"])
@limiter.limit("5/minute")
def reset_password(request: Request, body: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = consume_password_reset_token(body.token, db)
    user.hashed_password = hash_password(body.password)
    revoke_all_user_refresh_tokens(user.id, db)
    db.commit()
    write_audit(db, "password.reset", user_id=user.id, entity_type="user", entity_id=user.id,
                ip_address=_client_ip(request))
    return MessageResponse(message="Password reset successfully. You can now log in.")


@app.post("/api/auth/resend-verification", response_model=MessageResponse, tags=["Auth"])
@limiter.limit("3/minute")
def resend_verification(request: Request, body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    # Generic response regardless of whether the account exists (no account leakage)
    if not user or user.is_email_verified:
        return MessageResponse(message="Verification email sent")
    token = create_email_verification_token(user, db)
    send_verification_email(user.email, token)
    write_audit(db, "email.resend", user_id=user.id, entity_type="user", entity_id=user.id,
                ip_address=_client_ip(request))
    return MessageResponse(message="Verification email sent")


# ──────────────────────────────────────────────
#  DATA UPLOAD ROUTES
# ──────────────────────────────────────────────

@app.post("/api/data/upload", response_model=DatasetResponse, tags=["Data"])
@limiter.limit("10/minute")
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    safe_filename = _safe_filename(file.filename or "upload")
    ext = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not supported")

    content = await file.read()
    file_size = len(content)
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    try:
        df = read_uploaded_file(content, safe_filename)
        data_quality = assess_data_quality(df)
        df = clean_dataframe(df)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to parse upload %s: %s", safe_filename, e)
        raise HTTPException(status_code=400, detail="Failed to read file. Ensure it is a valid CSV, TSV, JSON, Excel or PDF.")

    if df.empty:
        raise HTTPException(status_code=400, detail="File contains no valid data after cleaning")

    table_id = str(uuid.uuid4()).replace("-", "")[:12]
    table_name = f"ds_{table_id}"
    dataset_name = (name or safe_filename.rsplit(".", 1)[0]).strip()[:255] or "Untitled dataset"

    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False, chunksize=500)
    except Exception as e:
        logger.error("Failed to store dataset %s: %s", table_name, e)
        raise HTTPException(status_code=500, detail="Failed to store data. Please try again.")

    columns_info = get_column_info(df)
    dataset = Dataset(
        name=dataset_name,
        original_filename=safe_filename,
        file_type=ext,
        table_name=table_name,
        row_count=len(df),
        column_count=len(df.columns),
        columns_info=columns_info,
        file_size=file_size,
        owner_id=current_user.id,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    clear_query_cache()

    write_audit(db, "dataset.upload", user_id=current_user.id, entity_type="dataset",
                entity_id=dataset.id, details=f"table={table_name} rows={len(df)}",
                ip_address=_client_ip(request))

    response = DatasetResponse.model_validate(dataset)
    response.data_quality = data_quality
    return response


@app.get("/api/data/datasets", response_model=DatasetListResponse, tags=["Data"])
def list_datasets(
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    query = db.query(Dataset)
    if current_user.role != "admin":
        query = query.filter(Dataset.owner_id == current_user.id)
    total = query.count()
    datasets = (
        query.order_by(Dataset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return DatasetListResponse(
        datasets=[DatasetResponse.model_validate(d) for d in datasets],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/api/data/datasets/{dataset_id}", response_model=DatasetResponse, tags=["Data"])
def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return DatasetResponse.model_validate(_get_owned_dataset(dataset_id, current_user, db))


@app.get("/api/data/datasets/{dataset_id}/preview", response_model=DatasetPreviewResponse, tags=["Data"])
def preview_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    safe_sql = validate_sql(
        f'SELECT * FROM "{dataset.table_name}" LIMIT {PREVIEW_LIMIT}',
        allowed_tables=[dataset.table_name],
    )
    try:
        with engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, r)) for r in result.fetchall()]
    except Exception as e:
        logger.error("Preview failed for dataset %s: %s", dataset.id, e)
        raise HTTPException(status_code=500, detail="Failed to read dataset preview")

    serialized = []
    for row in rows:
        item = {}
        for k, v in row.items():
            item[k] = _json_safe(v)
        serialized.append(item)

    return DatasetPreviewResponse(
        dataset=DatasetResponse.model_validate(dataset),
        columns=columns,
        sample_rows=serialized,
    )


@app.get("/api/data/datasets/{dataset_id}/rows", response_model=DatasetRowsResponse, tags=["Data"])
def dataset_rows(
    dataset_id: str,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "",
    sort_dir: str = "asc",
    search: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Server-side paginated, sortable, searchable raw-data view for the Data
    Explorer. Read-only analytical query; column names are validated against the
    table schema and the search value is parameterized, so no dynamic SQL can be
    injected. Only ever fetches one page of rows from the DB."""
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    sort_dir = "asc" if sort_dir != "desc" else "desc"

    columns = json.loads(dataset.columns_info or "[]")
    col_names = [c.get("name") for c in columns if c.get("name")]
    if not col_names:
        try:
            with engine.connect() as conn:
                result = conn.execute(text(f'SELECT * FROM "{dataset.table_name}" LIMIT 1'))
                col_names = list(result.keys())
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to read dataset columns")

    safe_sort = sort_by if sort_by in col_names else None
    sql = f'SELECT * FROM "{dataset.table_name}"'
    params = {}
    if search:
        conditions = [f'CAST("{c}" AS TEXT) LIKE :search' for c in col_names]
        sql += " WHERE " + " OR ".join(conditions)
        params["search"] = f"%{search}%"
    if safe_sort:
        sql += f' ORDER BY "{safe_sort}" {"ASC" if sort_dir == "asc" else "DESC"} NULLS LAST'
    else:
        sql += ' ORDER BY rowid'
    sql += f" LIMIT {page_size} OFFSET {(page - 1) * page_size}"

    validated_sql = validate_sql(sql, allowed_tables=[dataset.table_name])
    count_sql = f'SELECT COUNT(*) FROM "{dataset.table_name}"'
    if search:
        conditions = [f'CAST("{c}" AS TEXT) LIKE :search' for c in col_names]
        count_sql += " WHERE " + " OR ".join(conditions)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(validated_sql), params)
            columns_result = list(result.keys())
            rows = [dict(zip(columns_result, r)) for r in result.fetchall()]
            total = conn.execute(text(count_sql), params).scalar() or 0
    except Exception as e:
        logger.error("Rows query failed for dataset %s: %s", dataset.id, e)
        raise HTTPException(status_code=500, detail="Failed to read dataset rows")

    serialized = []
    for row in rows:
        item = {}
        for k, v in row.items():
            item[k] = _json_safe(v)
        serialized.append(item)

    unique_ratio = {
        c.get("name"): (c.get("unique") or 0) / max(1, dataset.row_count or 1)
        for c in columns if c.get("name") and c.get("unique") is not None
    }

    return DatasetRowsResponse(
        dataset=DatasetResponse.model_validate(dataset),
        columns=columns_result,
        rows=serialized,
        total=total,
        page=page,
        page_size=page_size,
        sorted_by=safe_sort,
        sorted_dir=sort_dir,
        search=search,
        row_count=dataset.row_count or 0,
        unique_ratio=unique_ratio,
    )


@app.get("/api/data/datasets/{dataset_id}/profile", response_model=DatasetProfileResponse, tags=["Data"])
def dataset_profile(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dataset overview + automatic insights for the dashboard. Reuses the column
    metadata captured at upload time; runs only cheap SQL for values that cannot
    be derived from metadata alone (date range, per-category totals)."""
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    cols_meta = _parse_columns_info(dataset.columns_info or "") if dataset.columns_info else []
    profile = build_profile(dataset, cols_meta, engine)
    return DatasetProfileResponse(
        dataset=DatasetResponse.model_validate(dataset),
        currency=profile["currency"],
        overview=profile["overview"],
        insights=profile["insights"],
    )


@app.get("/api/data/datasets/{dataset_id}/questions", response_model=DatasetQuestionsResponse, tags=["Data"])
def dataset_questions(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Schema-aware quick questions, generated from the dataset's actual columns."""
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    cols_meta = _parse_columns_info(dataset.columns_info or "") if dataset.columns_info else []
    qg = generate_quick_questions(cols_meta)
    return DatasetQuestionsResponse(
        overview=qg["overview"],
        category=qg["category"],
        insights=qg["insights"],
    )


@app.delete("/api/data/datasets/{dataset_id}", response_model=MessageResponse, tags=["Data"])
def delete_dataset(
    dataset_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    table_name = dataset.table_name

    _drop_table(table_name)
    db.delete(dataset)
    db.commit()
    clear_query_cache(dataset_id)

    write_audit(db, "dataset.delete", user_id=current_user.id, entity_type="dataset",
                entity_id=dataset_id, details=f"table={table_name}", ip_address=_client_ip(request))

    # Opportunistic cleanup of orphaned dynamic tables
    _cleanup_orphan_tables(db)

    return MessageResponse(message="Dataset deleted successfully")


# ──────────────────────────────────────────────
#  QUERY PIPELINE HELPERS
# ──────────────────────────────────────────────

VAGUE_QUESTIONS = {
    "tell me something", "tell me", "tell me more", "hello", "hi", "hey",
    "what can you do", "help", "help me", "what should i ask", "anything",
    "surprise me", "what else", "give me something", "analyze", "analyze this",
    "explore", "suggest", "suggest something", "give me a question",
}

_TREND_WORDS = ("trend", "over time", "monthly", "weekly", "daily", "yearly", "timeline", "growth")


def _is_trend_question(question: str) -> bool:
    q = question.lower()
    return any(w in q for w in _TREND_WORDS)


def _detect_id_aggregation_guidance(question: str, cols_meta: list) -> Optional[str]:
    """Semantic gate: flag attempts to SUM/AVERAGE an identifier column.

    ``SUM(supplierid)`` is technically valid SQL but semantically meaningless
    because ``supplierid`` is an identifier, not a measure. When the user asks
    for a total/average of an ID column we explain why and suggest meaningful
    alternatives instead of generating the misleading SQL. Legitimate ID
    questions (highest/lowest ID, how many, grouped distributions) are not
    rejected: only the meaningless additive aggregations are.
    """
    q = " " + question.lower() + " "
    id_cols = [c.get("name") for c in cols_meta if c.get("type") == "id"]
    if not id_cols:
        return None

    def _mentions(token: str) -> bool:
        # Token-aware match that also treats "_" as a separator, so both
        # "supplier_id" and "supplier id" match, regardless of trailing
        # punctuation ("what is the total supplier_id?").
        patterns = (token, token.replace("_", " "))
        return any(
            re.search(r"(?<![\w])" + re.escape(p) + r"(?![\w])", q)
            for p in patterns
        )

    mentioned = [c for c in id_cols if _mentions(c.lower())]
    if not mentioned:
        return None
    # Legitimate identifier questions that must still be allowed.
    if any(kw in q for kw in (
        "highest", "lowest", "maximum", "minimum", " max ", " min ",
        "how many", "number of", "count", "distinct", "distribution",
        " by ", " per ", " top ", " bottom ", "list", "show", "which",
        "range", "between",
    )):
        return None
    if not any(kw in q for kw in ("total", "sum", "average", "avg", "mean",
                                  "add", "add up", "aggregate", "summation")):
        return None
    col = mentioned[0]
    return (
        f"'{col}' is an identifier column, not a business measure. "
        f"Adding or averaging an ID produces a number without business meaning "
        f"(e.g. SUM({col}) just adds up arbitrary identifiers). "
        f"Did you mean: how many records there are, the highest {col}, "
        f"or a breakdown by a category column?"
    )


def _date_capable(cols_meta: list) -> bool:
    for c in cols_meta:
        name = (c.get("name") or "").lower()
        ctype = str(c.get("type") or "")
        if ctype == "date" or any(h in name for h in ("date", "time", "month", "year", "quarter", "week", "day")):
            return True
    return False


_PIPELINE_STAGES = [
    ("Question understanding", "Understand what the question asks and what it expects back."),
    ("Schema inspection", "Inspect the uploaded tables, their columns and value shapes."),
    ("Required-data check", "Verify the data needed for a real answer actually exists."),
    ("Multi-table relationship check", "Detect verified links between the selected tables."),
    ("Relevant column selection", "Pick the numeric, categorical and date columns for the answer."),
    ("SQL generation", "Translate the question into a validated SELECT query."),
    ("Safety validation", "Ensure the SQL is read-only and touches only the selected data."),
    ("Query execution", "Run the query against the database."),
    ("Result validation", "Verify the result actually answers the question."),
    ("Chart selection", "Pick a chart that matches the data shape without misleading."),
    ("Summary & insights", "Describe the result, risks and grounded next steps."),
]


def _pipeline(n_done: int) -> list:
    """Build the pipeline-stage list; stages after ``n_done`` are accurately
    marked as skipped so the UI never shows steps that did not run."""
    return [
        {"stage": name, "status": "done" if i < n_done else "skipped", "detail": detail}
        for i, (name, detail) in enumerate(_PIPELINE_STAGES)
    ]


def _owned_datasets(ids: list, current_user: User, db: Session) -> list:
    """Load and own-check a list of dataset IDs, deduplicated, in order."""
    unique_ids = list(dict.fromkeys(ids))
    datasets = [_get_owned_dataset(did, current_user, db) for did in unique_ids]
    return datasets


def _guidance_response(question: str, message: str, cols_meta: list, n_stages: int,
                       db: Session, current_user: User, dataset: Dataset,
                       answer_status: str = "clarification",
                       sufficiency: dict = None,
                       datasets_used: list = None) -> QueryResultResponse:
    """Friendly, honest response for questions the pipeline should not answer
    (vague prompts, time trends on datasets without a date column, questions the
    uploaded data cannot support)."""
    db.add(
        QueryLog(
            user_id=current_user.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            question=question,
            is_successful=answer_status == "answered",
            error_message=message if answer_status != "answered" else None,
        )
    )
    db.commit()

    ai_quality = generate_ai_quality(
        question, "", "table",
        {"valid": False, "issues": [message], "suggested_fix": None},
        data_length=0, sql_success=False,
        columns_info=json.dumps(cols_meta) if cols_meta else "",
        sufficiency_verdict=sufficiency,
    )
    follow_ups = generate_guidance_questions(cols_meta) if cols_meta else []
    return QueryResultResponse(
        question=question,
        generated_sql="",
        data=[],
        chart_type="table",
        chart_config={
            "chart_type": "table",
            "x_axis": "",
            "y_axis": "",
            "title": "Guidance",
            "description": message,
        },
        summary={
            "executive_summary": [message],
            "recommendations": [],
            "risks": [],
            "follow_up_questions": follow_ups,
        },
        follow_up_questions=follow_ups,
        ai_quality=ai_quality,
        validation_info={"valid": False, "issues": [message], "suggested_fix": None},
        pipeline_stages=_pipeline(n_stages),
        currency=None,
        answer_status=answer_status,
        sufficiency=sufficiency or {},
        datasets_used=[d.get("table_name") for d in (datasets_used or [])],
    )


def _insufficient_response(question: str, verdict: dict, cols_meta: list,
                           db: Session, current_user: User, datasets: list) -> QueryResultResponse:
    """Response when the sufficiency gate stops the pipeline: the question is
    not answerable from the uploaded data (or is ambiguous). The pipeline stops
    at the required-data stage instead of fabricating a numeric answer."""
    message = verdict.get("message") or "The uploaded data cannot answer this question."
    primary = datasets[0]
    cols_meta = cols_meta or _parse_columns_info(primary.columns_info or "")
    n_stages = 3  # stops at "Required-data check"
    ai_quality = generate_ai_quality(
        question, "", "table",
        {"valid": False, "issues": [message], "suggested_fix": None},
        data_length=0, sql_success=False,
        columns_info=json.dumps(cols_meta) if cols_meta else "",
        sufficiency_verdict=verdict,
    )
    follow_ups = generate_guidance_questions(cols_meta) if cols_meta else []

    required = verdict.get("required") or []
    available = verdict.get("available") or []
    missing = verdict.get("missing") or []

    detail = message
    if missing:
        detail += " Missing: " + "; ".join(missing) + "."
    if required:
        detail += " Would need: " + "; ".join(required) + "."

    return QueryResultResponse(
        question=question,
        generated_sql="",
        data=[],
        chart_type="table",
        chart_config={
            "chart_type": "table",
            "x_axis": "",
            "y_axis": "",
            "title": "Data does not support this question",
            "description": detail,
        },
        summary={
            "executive_summary": [message],
            "recommendations": [],
            "risks": ["Answering this question from the current data would be misleading."],
            "follow_up_questions": follow_ups,
        },
        follow_up_questions=follow_ups,
        ai_quality=ai_quality,
        validation_info={"valid": False, "issues": [message], "suggested_fix": None},
        pipeline_stages=_pipeline(n_stages),
        currency=None,
        answer_status="insufficient" if verdict.get("status") == "insufficient" else "clarification",
        sufficiency=verdict,
        datasets_used=[d.table_name for d in datasets],
    )


def _compute_enrichment(serialized_rows: list, cols_meta: list, dataset: Dataset, currency) -> dict:
    """For single-row aggregate results, compute the category breakdown so
    summaries can name the leading category without guessing."""
    if len(serialized_rows) != 1:
        return {}
    groups = classify_columns(cols_meta)
    metric = _preferred_metric(groups["numeric"])
    dim = _preferred_category(groups["categorical"])
    if not metric or not dim or not dataset.table_name:
        return {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                f'SELECT "{dim}", SUM("{metric}") AS v FROM "{dataset.table_name}" GROUP BY 1 ORDER BY v DESC LIMIT 4'
            )).fetchall()
            total = conn.execute(text(
                f'SELECT COALESCE(SUM("{metric}"), 0) FROM "{dataset.table_name}"'
            )).fetchone()[0]
    except Exception as e:
        logger.warning("Enrichment failed for dataset %s: %s", dataset.id, e)
        return {}
    return {
        "metric": metric,
        "dimension": dim,
        "by_dimension": [[r[0], float(r[1])] for r in rows],
        "total": float(total),
        "row_count": dataset.row_count,
        "currency": currency,
    }


# ──────────────────────────────────────────────
#  QUERY ROUTES
# ──────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResultResponse, tags=["Query"])
@limiter.limit("60/minute")
def execute_nl_query(
    request: Request,
    body: NLQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Load the primary dataset and, when provided, the additional datasets for
    # multi-dataset analysis (relationships/JOINs).
    primary = _get_owned_dataset(body.dataset_id, current_user, db)
    datasets = _owned_datasets([body.dataset_id] + (body.dataset_ids or []), current_user, db)
    if len(datasets) == 1:
        datasets = [primary]
    multi = len(datasets) > 1

    primary_columns_info = primary.columns_info or ""
    cols_meta = _parse_columns_info(primary_columns_info) if primary_columns_info else []
    datasets_meta = [
        {
            "id": d.id,
            "name": d.name,
            "table_name": d.table_name,
            "columns_info": d.columns_info or "",
            "row_count": d.row_count,
        }
        for d in datasets
    ]

    question = body.question.strip()
    pipeline_start = time.perf_counter()
    timings: dict = {}

    # ── CONVERSATION CONTEXT (AI Data Analyst) ─────────────────────────────
    # Follow-ups ("show me by region", "which one is worst?") are resolved
    # against the last turn on the same dataset before any other pipeline stage.
    if body.context:
        previous = next(
            (t for t in reversed(body.context) if t.dataset_id == body.dataset_id),
            None,
        )
        if previous:
            resolved = resolve_followup_question(
                question,
                {"question": previous.question, "sql": previous.sql, "columns": previous.columns},
                cols_meta,
            )
            if resolved != question:
                logger.info(
                    "Context resolution: %r -> %r (dataset %s)",
                    question, resolved, primary.id,
                )
                question = resolved
    timings["context_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 1)

    # ── RESULT CACHE ───────────────────────────────────────────────────────
    # Identical analysis on unchanged data returns instantly. Cached entries
    # are invalidated on dataset upload/delete and keyed by schema version, so
    # stale results can never be served.
    cache_key = None
    if not multi:
        cache_key = build_cache_key(
            current_user.id, primary.id, question,
            primary_columns_info, primary.row_count,
        )
        cached = get_cached(cache_key)
        if cached is not None:
            timings["cached"] = True
            timings["total_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 1)
            cached.pipeline_timings_ms = timings
            return cached
    timings["schema_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 1)
    timings["cached"] = False

    # Guidance: vague prompt -> suggest schema-aware questions instead of guessing.
    if question.lower().rstrip("!.") in VAGUE_QUESTIONS:
        return _guidance_response(
            question,
            "I can help you explore this dataset. Try asking about totals, averages, "
            "top items, comparisons across categories, or ask me for a full analysis.",
            cols_meta, n_stages=2, db=db, current_user=current_user, dataset=primary,
        )

    # Guidance: time trend on a dataset without any date/time column.
    if _is_trend_question(question) and not _date_capable(cols_meta):
        return _guidance_response(
            question,
            "This dataset doesn't contain a date/time column, so I can't calculate a "
            "time-based trend. Try comparing values across categories instead.",
            cols_meta, n_stages=2, db=db, current_user=current_user, dataset=primary,
        )

    # Guidance: ambiguous ("What is the best product?") and unsupported
    # ("Why did sales decrease?") questions are answered honestly instead of
    # fabricating a SQL answer.
    feasibility = check_question_feasibility(question, cols_meta)
    if feasibility["guidance"]:
        return _guidance_response(
            question,
            feasibility["guidance"],
            cols_meta, n_stages=2, db=db, current_user=current_user, dataset=primary,
        )

    # ── SEMANTIC GATE (identifier aggregation) ─────────────────────────────
    # "What is the total supplierid?" must never run SUM(supplierid).
    id_guidance = _detect_id_aggregation_guidance(question, cols_meta)
    if id_guidance:
        return _guidance_response(
            question, id_guidance, cols_meta, n_stages=3,
            db=db, current_user=current_user, dataset=primary,
        )

    # ── SUFFICIENCY GATE (primary prevention of wrong answers) ──────────────
    # Before any SQL is generated, verify the required data actually exists. The
    # critical bug pattern ("How many customers purchased two items together?"
    # answered with COUNT(*) over a customer directory) is stopped here.
    suff = check_sufficiency(question, datasets_meta)
    if suff["status"] in ("insufficient", "ambiguous"):
        return _insufficient_response(question, suff, cols_meta, db, current_user, datasets)

    # ── SQL GENERATION ──────────────────────────────────────────────────────
    multi_plan = None
    if multi:
        relationships = detect_relationships(engine, datasets_meta)
        multi_plan = build_multi_table_sql(question, datasets_meta, relationships)

    if multi_plan:
        generated_sql = multi_plan["sql"]
        validation_result = validate_sql_intent_multi(question, generated_sql, datasets_meta)
        used_tables = multi_plan.get("tables_used") or [d.table_name for d in datasets]
        if not validation_result["valid"]:
            # Fall back to the single-table path rather than surfacing bad SQL.
            generated_sql = None
        else:
            generation_route = "join"

    if not multi_plan:
        generated_sql = nl_to_sql(question, primary.table_name, primary_columns_info)
        used_tables = [primary.table_name]
        generation_route = "ai" if USE_AI else "local"

    if generated_sql and generated_sql.startswith("AI_ERROR"):
        logger.error("AI provider error for question %r: %s", question, generated_sql)
        db.add(
            QueryLog(
                user_id=current_user.id,
                dataset_id=primary.id,
                dataset_name=primary.name,
                question=question,
                is_successful=False,
                error_message="AI service unavailable",
            )
        )
        db.commit()
        raise HTTPException(
            status_code=502,
            detail="The AI service is temporarily unavailable. Please try again later.",
        )

    if generated_sql is None:
        # Join plan failed validation -> regenerate against the primary table.
        generated_sql = nl_to_sql(question, primary.table_name, primary_columns_info)
        used_tables = [primary.table_name]
        generation_route = "ai" if USE_AI else "local"

    if generation_route != "join":
        validation_result = validate_sql_intent(question, generated_sql, primary.table_name, primary_columns_info)

    # Auto-regenerate if validation fails: retry the AI once, then fall back to
    # the deterministic local engine, which is schema-grounded and always
    # produces validatable SQL. Never surface an invalid AI query to execution.
    if not validation_result["valid"] and generation_route != "join":
        regenerated_sql = nl_to_sql(question, primary.table_name, primary_columns_info)
        revalidation = validate_sql_intent(question, regenerated_sql, primary.table_name, primary_columns_info)
        if revalidation["valid"]:
            generated_sql = regenerated_sql
            validation_result = revalidation
        else:
            local_sql = _local_nl_to_sql(question, primary.table_name, primary_columns_info)
            local_validation = validate_sql_intent(question, local_sql, primary.table_name, primary_columns_info)
            if local_validation["valid"]:
                generated_sql = local_sql
                validation_result = local_validation
            else:
                generated_sql = regenerated_sql
                validation_result["issues"].extend(revalidation["issues"])

    # Safety validate SQL against the exact set of tables the query may touch.
    try:
        safe_sql = validate_sql(generated_sql, allowed_tables=used_tables)
    except HTTPException:
        raise

    # Execute query (capped at RESULT_LIMIT rows)
    try:
        with engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            columns = list(result.keys())
            raw_rows = result.fetchmany(RESULT_LIMIT + 1)
            rows = [dict(zip(columns, r)) for r in raw_rows[:RESULT_LIMIT]]
    except Exception as e:
        logger.error("SQL execution failed for dataset %s: %s", primary.id, e)
        db.add(
            QueryLog(
                user_id=current_user.id,
                dataset_id=primary.id,
                dataset_name=primary.name,
                question=question,
                generated_sql=safe_sql,
                is_successful=False,
                error_message="SQL execution failed",
            )
        )
        db.commit()
        suggested_fix = _local_nl_to_sql(question, primary.table_name, primary_columns_info)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "The query could not be executed. The generated SQL may be incompatible with this dataset.",
                "generated_sql": safe_sql,
                "question": question,
                "suggested_fix": suggested_fix,
                "error_type": "sql_execution",
            },
        )

    # Serialize data
    serialized_rows = []
    for row in rows:
        serialized = {}
        for k, v in row.items():
            serialized[k] = _json_safe(v)
        serialized_rows.append(serialized)

    # ── POST-EXECUTION RESULT VALIDATION (second net) ───────────────────────
    result_verdict = validate_result(question, columns, serialized_rows, cols_meta, safe_sql)

    # Detect chart type
    chart_config = detect_chart_type(question, columns, serialized_rows)
    chart_type = chart_config.get("chart_type", "table")

    # Enrich single-row aggregate results with a real category breakdown + currency
    groups = classify_columns(cols_meta) if cols_meta else {}
    currency = detect_currency(primary.name, groups.get("numeric", []) + groups.get("categorical", []))
    enrichment = _compute_enrichment(serialized_rows, cols_meta, primary, currency)

    # Semantic types per result column: COUNT results are never currency, only
    # genuinely monetary fields get currency formatting.
    semantic_types = analyze_sql_semantics(safe_sql, columns, cols_meta, serialized_rows)

    # Generate insights (capability-aware, schema-aware, result-aware)
    insights = generate_insights(
        question, serialized_rows, columns, primary_columns_info,
        enrichment=enrichment, dataset_name=primary.name,
        semantic_types=semantic_types,
    )

    # Generate AI quality indicators with capability-aware confidence
    ai_quality = generate_ai_quality(
        question, safe_sql, chart_type, validation_result,
        data_length=len(serialized_rows), sql_success=True,
        columns_info=primary_columns_info,
        sufficiency_verdict=suff,
        result_verdict=result_verdict,
    )

    # Answer status contract: answered / insufficient / clarification / failed
    if result_verdict["status"] == "invalid":
        answer_status = "failed"
    elif result_verdict["status"] == "questionable":
        answer_status = "answered"
    else:
        answer_status = "answered"

    validation_info = {
        "valid": validation_result["valid"],
        "issues": validation_result["issues"],
        "suggested_fix": validation_result.get("suggested_fix"),
    }

    db.add(
        QueryLog(
            user_id=current_user.id,
            dataset_id=primary.id,
            dataset_name=primary.name,
            question=question,
            generated_sql=safe_sql,
            result_summary=json.dumps(insights.get("executive_summary", [])),
            chart_type=chart_type,
            row_count=len(serialized_rows),
            is_successful=answer_status == "answered",
        )
    )
    db.commit()

    timings["total_ms"] = round((time.perf_counter() - pipeline_start) * 1000, 1)

    response = QueryResultResponse(
        question=question,
        generated_sql=safe_sql,
        data=serialized_rows,
        chart_type=chart_type,
        chart_config=chart_config,
        summary=insights,
        follow_up_questions=insights.get("follow_up_questions", []),
        ai_quality=ai_quality,
        validation_info=validation_info,
        pipeline_stages=_pipeline(len(_PIPELINE_STAGES)),
        currency=currency,
        semantic_types=semantic_types,
        answer_status=answer_status,
        sufficiency=suff,
        datasets_used=[d.table_name for d in datasets],
        pipeline_timings_ms=timings,
    )
    if cache_key is not None:
        put_cached(cache_key, response, dataset_ids=[d.id for d in datasets])
    return response


@app.get("/api/query/history", response_model=QueryLogListResponse, tags=["Query"])
def query_history(
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    query = db.query(QueryLog).filter(QueryLog.user_id == current_user.id)
    total = query.count()
    logs = (
        query.order_by(QueryLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return QueryLogListResponse(
        queries=[QueryLogResponse.model_validate(l) for l in logs],
        total=total,
    )


@app.delete("/api/query/history/{query_id}", tags=["Query"])
def delete_history_entry(
    query_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log = (
        db.query(QueryLog)
        .filter(QueryLog.id == query_id, QueryLog.user_id == current_user.id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="History entry not found")
    db.delete(log)
    db.commit()
    return {"deleted": query_id}


@app.delete("/api/query/history", tags=["Query"])
def clear_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deleted = (
        db.query(QueryLog)
        .filter(QueryLog.user_id == current_user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


# ──────────────────────────────────────────────
#  ADMIN ROUTES
# ──────────────────────────────────────────────

@app.get("/api/admin/users", response_model=List[UserResponse], tags=["Admin"])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [UserResponse.model_validate(u) for u in users]


@app.patch("/api/admin/users/{user_id}", response_model=UserResponse, tags=["Admin"])
def update_user(
    user_id: str,
    body: UserAdminUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account here")

    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            revoke_all_user_refresh_tokens(user.id, db)
    if body.role is not None:
        user.role = body.role
    db.commit()
    db.refresh(user)

    write_audit(db, "admin.user.update", user_id=admin.id, entity_type="user",
                entity_id=user.id, details=f"active={user.is_active} role={user.role}",
                ip_address=_client_ip(request))
    return UserResponse.model_validate(user)


# ──────────────────────────────────────────────
#  HEALTH
# ──────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "GenAI BI Platform",
        "version": "2.0.0",
        "database": "ok" if db_ok else "unavailable",
        "ai_provider": provider_info(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
