import os
import json
import uuid
import math
from typing import List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv

from database import get_db, init_db, engine
from models import User, Dataset, QueryLog, AuthLog
from schemas import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    DatasetResponse, DatasetListResponse,
    NLQueryRequest, QueryResultResponse, QueryLogResponse,
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin,
)
from data_cleaner import read_uploaded_file, clean_dataframe, get_column_info, analyze_dataset
from sql_validator import validate_sql, sanitize_column_name
from ai_engine import nl_to_sql, _local_nl_to_sql, detect_chart_type, generate_insights, generate_ai_quality, validate_sql_intent

load_dotenv()

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://0.0.0.0:3000",
    "https://genaibi.vercel.app",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="GenAI BI Platform",
    description="Natural Language Business Intelligence powered by Generative AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
#  AUTH ROUTES
# ──────────────────────────────────────────────

@app.post("/api/auth/register", response_model=TokenResponse, tags=["Auth"])
def register(body: UserCreate, request: Request, db: Session = Depends(get_db)):
    ip_addr = request.client.host if request.client else None
    
    # Check existing email
    if db.query(User).filter(User.email == body.email).first():
        log = AuthLog(
            email=body.email,
            username=body.username,
            attempt_type="register",
            is_successful=False,
            error_message="Email already registered",
            ip_address=ip_addr
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # Check existing username
    if db.query(User).filter(User.username == body.username).first():
        log = AuthLog(
            email=body.email,
            username=body.username,
            attempt_type="register",
            is_successful=False,
            error_message="Username already taken",
            ip_address=ip_addr
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log = AuthLog(
        email=body.email,
        username=body.username,
        attempt_type="register",
        is_successful=True,
        ip_address=ip_addr
    )
    db.add(log)
    db.commit()

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
def login(body: UserLogin, request: Request, db: Session = Depends(get_db)):
    ip_addr = request.client.host if request.client else None
    user = db.query(User).filter(User.email == body.email).first()
    
    if not user or not verify_password(body.password, user.hashed_password):
        log = AuthLog(
            email=body.email,
            username=user.username if user else None,
            attempt_type="login",
            is_successful=False,
            error_message="Invalid credentials",
            ip_address=ip_addr
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not user.is_active:
        log = AuthLog(
            email=body.email,
            username=user.username,
            attempt_type="login",
            is_successful=False,
            error_message="Account disabled",
            ip_address=ip_addr
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=403, detail="Account disabled")

    log = AuthLog(
        email=body.email,
        username=user.username,
        attempt_type="login",
        is_successful=True,
        ip_address=ip_addr
    )
    db.add(log)
    db.commit()

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@app.get("/api/auth/me", response_model=UserResponse, tags=["Auth"])
def get_profile(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


# ──────────────────────────────────────────────
#  DATA UPLOAD ROUTES
# ──────────────────────────────────────────────

@app.post("/api/data/upload", response_model=DatasetResponse, tags=["Data"])
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_ext = {"csv", "xlsx", "xls", "pdf"}
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not supported")

    content = await file.read()
    file_size = len(content)
    if file_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    try:
        df = read_uploaded_file(content, file.filename)
        df = clean_dataframe(df)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="File contains no valid data after cleaning")

    table_id = str(uuid.uuid4()).replace("-", "")[:12]
    table_name = f"ds_{table_id}"
    dataset_name = name or file.filename.rsplit(".", 1)[0]

    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False, chunksize=500)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store data: {str(e)}")

    columns_info = get_column_info(df)
    dataset = Dataset(
        id=str(uuid.uuid4()),
        name=dataset_name,
        original_filename=file.filename,
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

    return DatasetResponse.model_validate(dataset)


@app.get("/api/data/datasets", response_model=DatasetListResponse, tags=["Data"])
def list_datasets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == "admin":
        datasets = db.query(Dataset).order_by(Dataset.created_at.desc()).all()
    else:
        datasets = (
            db.query(Dataset)
            .filter(Dataset.owner_id == current_user.id)
            .order_by(Dataset.created_at.desc())
            .all()
        )
    return DatasetListResponse(
        datasets=[DatasetResponse.model_validate(d) for d in datasets],
        total=len(datasets),
    )


@app.get("/api/data/datasets/{dataset_id}", response_model=DatasetResponse, tags=["Data"])
def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if current_user.role != "admin" and dataset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return DatasetResponse.model_validate(dataset)


@app.delete("/api/data/datasets/{dataset_id}", tags=["Data"])
def delete_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if current_user.role != "admin" and dataset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Drop the data table
    with engine.connect() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{dataset.table_name}"'))
        conn.commit()

    db.delete(dataset)
    db.commit()
    return {"message": "Dataset deleted successfully"}


# ──────────────────────────────────────────────
#  QUERY ROUTES
# ──────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResultResponse, tags=["Query"])
def execute_nl_query(
    body: NLQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # ── Debug logging ──
    print(f"[QUERY] Received dataset_id: '{body.dataset_id}' (type: {type(body.dataset_id).__name__}, len: {len(body.dataset_id)})")
    print(f"[QUERY] Question: '{body.question}'")

    dataset = db.query(Dataset).filter(Dataset.id == body.dataset_id).first()
    if not dataset:
        # Try fallback: trim/cast in case of whitespace issues
        cleaned_id = body.dataset_id.strip()
        if cleaned_id != body.dataset_id:
            dataset = db.query(Dataset).filter(Dataset.id == cleaned_id).first()
        if not dataset:
            print(f"[QUERY] Dataset NOT FOUND for ID: '{body.dataset_id}'")
            # Log all dataset IDs in DB for debugging
            all_ids = [d.id for d in db.query(Dataset.id).all()]
            print(f"[QUERY] Available dataset IDs in DB: {all_ids}")
            raise HTTPException(
                status_code=404,
                detail=f"Dataset not found. Received ID: '{body.dataset_id}'"
            )
    print(f"[QUERY] Dataset found: '{dataset.name}' (table: {dataset.table_name})")

    if current_user.role != "admin" and dataset.owner_id != current_user.id:
        print(f"[QUERY] Access denied: user {current_user.id} cannot access dataset owned by {dataset.owner_id}")
        raise HTTPException(status_code=403, detail="Access denied")

    # Parse columns info for validation
    columns_info = dataset.columns_info or ""
    cols_parsed = json.loads(columns_info) if columns_info else []
    col_names = [c["name"] for c in cols_parsed]

    # Generate SQL
    generated_sql = nl_to_sql(body.question, dataset.table_name, columns_info)

    if generated_sql.startswith("AI_ERROR"):
        log = QueryLog(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            question=body.question,
            generated_sql=None,
            is_successful=False,
            error_message=generated_sql,
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=500, detail=generated_sql)

    # Validate SQL intent - check if SQL matches user intent
    validation_result = validate_sql_intent(body.question, generated_sql, dataset.table_name, columns_info)

    # Auto-regenerate if validation fails
    if not validation_result["valid"]:
        regenerated_sql = nl_to_sql(body.question, dataset.table_name, columns_info)
        revalidation = validate_sql_intent(body.question, regenerated_sql, dataset.table_name, columns_info)
        if revalidation["valid"]:
            generated_sql = regenerated_sql
            validation_result = revalidation
        else:
            generated_sql = regenerated_sql
            validation_result["issues"].extend(revalidation["issues"])

    # Safety validate SQL
    safe_sql = validate_sql(generated_sql, allowed_tables=[dataset.table_name])

    # Execute query
    sql_error = None
    try:
        with engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
    except Exception as e:
        sql_error = str(e)
        log = QueryLog(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            question=body.question,
            generated_sql=safe_sql,
            is_successful=False,
            error_message=sql_error,
        )
        db.add(log)
        db.commit()
        # Return structured error with suggested fix
        suggested_fix = _local_nl_to_sql(body.question, dataset.table_name, columns_info)
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"SQL execution error: {str(e)}",
                "generated_sql": safe_sql,
                "question": body.question,
                "suggested_fix": suggested_fix,
                "error_type": "sql_execution",
            }
        )

    # Serialize data
    serialized_rows = []
    for row in rows:
        serialized = {}
        for k, v in row.items():
            if v is None:
                serialized[k] = None
            elif isinstance(v, (int, float, str, bool)):
                serialized[k] = v
            else:
                serialized[k] = str(v)
        serialized_rows.append(serialized)

    # Detect chart type
    chart_config = detect_chart_type(body.question, columns, serialized_rows)
    chart_type = chart_config.get("chart_type", "table")

    # Generate insights
    insights = generate_insights(body.question, serialized_rows, columns)

    # Generate AI quality indicators with 8-step scoring
    ai_quality = generate_ai_quality(
        body.question, safe_sql, chart_type, validation_result,
        data_length=len(serialized_rows), sql_success=True
    )

    # Build validation info for response
    validation_info = {
        "valid": validation_result["valid"],
        "issues": validation_result["issues"],
        "suggested_fix": validation_result.get("suggested_fix"),
    }

    # Log query
    log = QueryLog(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        question=body.question,
        generated_sql=safe_sql,
        result_summary=json.dumps(insights.get("executive_summary", [])),
        chart_type=chart_type,
        row_count=len(serialized_rows),
        is_successful=True,
    )
    db.add(log)
    db.commit()

    return QueryResultResponse(
        question=body.question,
        generated_sql=safe_sql,
        data=serialized_rows,
        chart_type=chart_type,
        chart_config=chart_config,
        summary=insights,
        follow_up_questions=insights.get("follow_up_questions", []),
        ai_quality=ai_quality,
        validation_info=validation_info,
    )


@app.get("/api/query/history", response_model=List[QueryLogResponse], tags=["Query"])
def query_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(QueryLog)
        .filter(QueryLog.user_id == current_user.id)
        .order_by(QueryLog.created_at.desc())
        .limit(50)
        .all()
    )
    return [QueryLogResponse.model_validate(l) for l in logs]


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


# ──────────────────────────────────────────────
#  HEALTH
# ──────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
def health_check():
    return {"status": "healthy", "service": "GenAI BI Platform"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
