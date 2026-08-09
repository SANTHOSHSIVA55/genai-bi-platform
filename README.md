# GenAI BI Platform

A production-oriented Business Intelligence platform powered by Generative AI. Upload CSV/Excel datasets, authenticate securely, and ask natural-language questions that are translated into SQL, validated, executed against your data, and rendered as interactive charts.

- **Backend**: FastAPI (Python 3.10+), SQLAlchemy, PostgreSQL (SQLite for dev), JWT auth with refresh-token rotation, rate limiting, audit logging, Alembic migrations.
- **Frontend**: React 18 + React Router, TailwindCSS, Recharts, React Three Fiber, Axios, React Hot Toast.
- **AI engine**: Optional LLM provider (NVIDIA NIM, OpenAI-compatible) with a fully deterministic local NL->SQL fallback so the platform works with no API key.

---

## Features

- **Natural Language to SQL**: Type questions like *"Show total revenue by region"* or *"Top 5 categories by units"`; the engine classifies the question (analysis / count / ranking / comparison / list / time-series), generates SQL, validates it (no `DELETE`, `DROP`, or multi-statement), and runs it against your dataset.
- **Capability-aware engine**: column metadata is classified (id / metric / date / categorical / text) and questions referencing data the dataset does not have are downgraded to a safe overview instead of misleading SQL.
- **Dataset management**: drag-and-drop CSV/Excel upload, cleaning, per-user dataset ownership, preview, delete.
- **Query history**: every query is recorded per user and can be re-run from the dashboard.
- **Secure authentication**: bcrypt (rounds=12), short-lived access JWTs, rotating single-use refresh tokens (SHA-256 hashed at rest), email verification, password reset, rate limiting, CORS allow-lists, admin RBAC, audit log.
- **Interactive visualizations**: results rendered as bar / line / area / pie charts with a premium dark UI.
- **Code-split frontend**: lazy-loaded routes keep the initial bundle small.

---

## Project Structure

```text
genai-bi-platform/
├── backend/
│   ├── main.py               # FastAPI app, routes, rate limits, middleware
│   ├── auth.py               # Password hashing, JWT, refresh-token rotation
│   ├── models.py             # SQLAlchemy models (users, datasets, queries, tokens, audit)
│   ├── schemas.py            # Pydantic validation schemas
│   ├── database.py           # Engine/session setup (Postgres or SQLite)
│   ├── data_cleaner.py       # CSV/Excel parsing & cleaning
│   ├── sql_validator.py      # SQL safety validation
│   ├── audit.py              # Audit-log writer
│   ├── logging_config.py     # Logging setup
│   ├── ai/                   # AI engine: provider, intent, sql_generator,
│   │   │                     #   chart_selector, insights, quality, columns
│   ├── services/email_service.py  # SMTP email (console fallback in dev)
│   ├── alembic/              # Database migrations
│   ├── tests/                # pytest suite (auth, datasets, queries)
│   ├── Dockerfile
│   ├── requirements.txt / requirements-dev.txt
│   └── .env.example
├── frontend/
│   ├── public/
│   └── src/
│       ├── api/              # Axios client, token store, refresh handling
│       ├── context/          # AuthContext
│       ├── components/       # Navbar, charts, modals, shared UI
│       ├── pages/            # Landing, Login, Register, Dashboard, Upload,
│       │                     #   History, VerifyEmail, ResetPassword, ...
│       ├── App.js            # Lazy routes + protected/guest routing
│       └── index.js
├── docker-compose.yml        # postgres + alembic migrate + api
└── .github/workflows/ci.yml  # CI: backend tests, frontend build, docker build
```

---

## Environment Variables

All backend settings live in `backend/.env` (see `backend/.env.example`):

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | e.g. `postgresql+psycopg2://user:pass@host:5432/db` (or `sqlite:///genai_bi.db` for dev) |
| `SECRET_KEY` | **Required in production.** Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ALGORITHM` | JWT algorithm (default `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access JWT lifetime (default 60) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime (default 30) |
| `PASSWORD_RESET_EXPIRE_MINUTES` | Reset token lifetime (default 60) |
| `EMAIL_VERIFY_EXPIRE_HOURS` | Email-verification token lifetime (default 24) |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `FRONTEND_URL` | Frontend origin used in emails |
| `NVIDIA_API_KEY` | Optional LLM provider key. Leave empty to use the local deterministic engine |
| `NVIDIA_MODEL` | Model name (default `deepseek-ai/deepseek-v4-pro`) |
| `NVIDIA_BASE_URL` | OpenAI-compatible base URL |
| `AI_TIMEOUT_SECONDS` / `AI_MAX_TOKENS` | LLM request tuning |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | Email. If `SMTP_HOST` is unset, emails print to the app log (dev) |
| `LOG_LEVEL` | Logging level (default `INFO`) |

Frontend (`frontend/.env`):

| Variable | Description |
| --- | --- |
| `REACT_APP_API_URL` | Backend base URL, e.g. `http://localhost:8000` |

---

## Local Development

Prerequisites: Python 3.10+, Node.js 18+.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
Copy-Item .env.example .env        # then edit values
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

Run migrations manually (SQLite dev database is auto-created by the app):

```bash
alembic upgrade head
```

### 2. Frontend

```bash
cd frontend
npm install
npm start        # http://localhost:3000
```

### 3. Docker (full stack: Postgres + migrations + API)

```bash
docker compose up --build
```

`SECRET_KEY` is mandatory for the `api` service; set it in the environment or a `.env` file (e.g. `SECRET_KEY=... POSTGRES_PASSWORD=... docker compose up --build`).

---

## Testing

Backend (runs against an isolated temp SQLite database; no network or AI key required):

```bash
cd backend
python -m pytest -q                    # full suite
python -m pytest --cov-report=term-missing --cov=main --cov=ai --cov=auth --cov=services -q
```

Frontend build (CI checks this):

```bash
cd frontend
npm run build
```

---

## API Overview

All endpoints (except auth/health) require `Authorization: Bearer <access_token>`.

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/auth/register` | Create account, returns access + refresh tokens |
| POST | `/api/auth/login` | Log in |
| POST | `/api/auth/refresh` | Rotate refresh token, issue new pair |
| POST | `/api/auth/logout` | Revoke refresh token(s) |
| GET | `/api/auth/me` | Current user profile |
| POST | `/api/auth/verify-email` | Verify email via token |
| POST | `/api/auth/forgot-password` | Request password reset (generic response) |
| POST | `/api/auth/reset-password` | Reset password via token |
| POST | `/api/auth/resend-verification` | Resend verification email (email-based, generic response) |
| POST | `/api/data/upload` | Upload CSV/Excel dataset (multipart) |
| GET | `/api/data/datasets` | List own datasets |
| GET | `/api/data/datasets/{id}` | Dataset detail |
| GET | `/api/data/datasets/{id}/preview` | Preview rows |
| DELETE | `/api/data/datasets/{id}` | Delete dataset |
| POST | `/api/query` | Run a natural-language query against a dataset |
| GET | `/api/query/history` | Query history |
| GET | `/api/admin/users` | List all users (admin only) |
| PATCH | `/api/admin/users/{id}` | Toggle user active/role (admin only) |
| GET | `/api/health` | Service health |

---

## CI

`.github/workflows/ci.yml` runs on push/PR to `main`/`master`:

1. **Backend**: installs `requirements-dev.txt`, runs the full pytest suite and a coverage report.
2. **Frontend**: `npm ci` + `npm run build`.
3. **Docker**: builds the backend image (and frontend if a Dockerfile is added).

---

## Security Notes

- `SECRET_KEY` must be a long random value and never committed.
- Access tokens are short-lived; refresh tokens are rotated on every use and stored hashed (SHA-256).
- Passwords are hashed with bcrypt (12 rounds).
- API responses are strict Pydantic schemas (no password hashes or raw tokens leaked).
- Dataset queries are ownership-checked (`_get_owned_dataset`), preventing IDOR across users.
- Generated SQL is validated before execution (SELECT-only, single statement, read-only).
- Rate limits via `slowapi`; admin routes require the `admin` role.
- A production deployment checklist is part of the final security audit — never ship with default credentials or the sample `SECRET_KEY`.
