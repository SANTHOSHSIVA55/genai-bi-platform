import os
import json
import uuid
from typing import List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv

from database import get_db, init_db, engine
from models import User, Dataset, QueryLog
from schemas import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    DatasetResponse, DatasetListResponse,
    NLQueryRequest, QueryResultResponse, QueryLogResponse,
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin,
)
from data_cleaner import read_uploaded_file, clean_dataframe, get_column_info
from sql_validator import validate_sql, sanitize_column_name
from ai_engine import nl_to_sql, detect_chart_type, generate_insights

load_dotenv()


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
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://0.0.0.0:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
#  AUTH ROUTES
# ──────────────────────────────────────────────

@app.post("/api/auth/register", response_model=TokenResponse, tags=["Auth"])
def register(body: UserCreate, db: Session = Depends(get_db)):
    # Check existing email
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    # Check existing username
    if db.query(User).filter(User.username == body.username).first():
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

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Auth"])
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

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
    if file_size > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    df = read_uploaded_file(content, file.filename)
    df = clean_dataframe(df)

    table_id = str(uuid.uuid4()).replace("-", "")[:12]
    table_name = f"ds_{table_id}"
    dataset_name = name or file.filename.rsplit(".", 1)[0]

    # Create table dynamically
    col_defs = []
    for col in df.columns:
        safe_col = sanitize_column_name(col)
        if df[col].dtype in ("int64", "int32"):
            col_defs.append(f'"{safe_col}" INTEGER')
        elif df[col].dtype in ("float64", "float32"):
            col_defs.append(f'"{safe_col}" REAL')
        elif str(df[col].dtype).startswith("datetime"):
            col_defs.append(f'"{safe_col}" TEXT')  # SQLite stores dates as TEXT
        else:
            col_defs.append(f'"{safe_col}" TEXT')

    create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'

    with engine.connect() as conn:
        conn.execute(text(create_sql))
        conn.commit()

        # Insert data in batches
        df.columns = [sanitize_column_name(c) for c in df.columns]
        for start in range(0, len(df), 500):
            batch = df.iloc[start:start + 500]
            for _, row in batch.iterrows():
                cols_str = ", ".join(f'"{c}"' for c in batch.columns)
                vals = []
                for c in batch.columns:
                    v = row[c]
                    if v is None or (hasattr(v, '__class__') and v.__class__.__name__ == 'NaTType'):
                        vals.append("NULL")
                    elif isinstance(v, (int, float)):
                        import math
                        if math.isnan(v):
                            vals.append("NULL")
                        else:
                            vals.append(str(v))
                    else:
                        escaped = str(v).replace("'", "''")
                        vals.append(f"'{escaped}'")
                vals_str = ", ".join(vals)
                insert_sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({vals_str})'
                conn.execute(text(insert_sql))
        conn.commit()

    # Save dataset metadata
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
    dataset = db.query(Dataset).filter(Dataset.id == body.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if current_user.role != "admin" and dataset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Generate SQL
    generated_sql = nl_to_sql(body.question, dataset.table_name, dataset.columns_info or "")

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

    # Validate SQL
    safe_sql = validate_sql(generated_sql, allowed_tables=[dataset.table_name])

    # Execute query
    try:
        with engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
    except Exception as e:
        log = QueryLog(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            question=body.question,
            generated_sql=safe_sql,
            is_successful=False,
            error_message=str(e),
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=400, detail=f"SQL execution error: {str(e)}")

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
