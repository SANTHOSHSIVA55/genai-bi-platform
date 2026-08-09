import os
import logging
from typing import List

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("app.database")


def _resolve_db_url() -> str:
    """Return the DATABASE_URL, preferring the env var and adapting local defaults."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # Default to a local SQLite database stored in the backend directory.
    if os.getenv("VERCEL"):
        db_path = "/tmp/genai_bi.db"
    else:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "genai_bi.db")
    return f"sqlite:///{db_path}"


DATABASE_URL = _resolve_db_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# SQLite needs check_same_thread=False when used with FastAPI threads.
connect_args = {}
if IS_SQLITE:
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns_sqlite() -> None:
    """Add newly-introduced columns to pre-existing local SQLite tables.

    This is a lightweight convenience migration for development databases that
    were created before new columns were added to the ORM models. Production
    environments should use Alembic migrations instead.
    """
    expected_columns: dict = {
        "users": ["is_email_verified", "last_login_at"],
    }
    try:
        inspector = inspect(engine)
        with engine.begin() as conn:
            for table, columns in expected_columns.items():
                if table not in inspector.get_table_names():
                    continue
                existing = {c["name"] for c in inspector.get_columns(table)}
                for column in columns:
                    if column in existing:
                        continue
                    if column == "is_email_verified":
                        ddl = 'ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN DEFAULT 0 NOT NULL'
                    elif column == "last_login_at":
                        ddl = "ALTER TABLE users ADD COLUMN last_login_at DATETIME"
                    else:
                        continue
                    conn.execute(text(ddl))
                    logger.info("Added missing column %s.%s", table, column)
    except Exception as exc:  # pragma: no cover - best-effort migration
        logger.warning("Lightweight SQLite column migration skipped: %s", exc)


def init_db() -> None:
    """Create all tables (used for local development / first run)."""
    from models import (  # noqa: F401
        User,
        Dataset,
        QueryLog,
        AuthLog,
        RefreshToken,
        PasswordResetToken,
        EmailVerification,
        AuditLog,
    )

    Base.metadata.create_all(bind=engine)
    if IS_SQLITE:
        _ensure_columns_sqlite()
    logger.info("Database initialized: %s", DATABASE_URL)


def get_dynamic_table_names() -> List[str]:
    """Return the names of dynamic dataset tables (prefix ds_)."""
    if IS_SQLITE:
        inspector = inspect(engine)
        return [
            t for t in inspector.get_table_names() if t.startswith("ds_")
        ]
    # PostgreSQL equivalent.
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename LIKE 'ds_%'"
            )
        ).fetchall()
        return [r[0] for r in rows]
