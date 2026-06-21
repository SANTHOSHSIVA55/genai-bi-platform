import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Use SQLite by default (zero-config, works everywhere)
# Set DATABASE_URL env var to switch to PostgreSQL in production
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "genai_bi.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# SQLite needs check_same_thread=False for FastAPI
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
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


def init_db():
    """Create all tables."""
    from models import User, Dataset, QueryLog  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print(f"[DB] Database initialized: {DATABASE_URL}")
