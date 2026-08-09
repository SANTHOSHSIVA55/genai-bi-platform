import io
import os
import tempfile
import uuid

# Env must be configured before the application is imported.
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), f"genai_bi_test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["NVIDIA_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

import main as main_module  # noqa: F401  (ensures app module is importable)
from main import app

CSV_CONTENT = (
    "category,revenue,units,region\n"
    "Electronics,1200,34,North\n"
    "Books,340,120,South\n"
    "Clothing,890,55,East\n"
    "Electronics,1500,41,West\n"
    "Books,210,95,North\n"
)


def _unique(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _unique_email(local="user"):
    return f"{_unique(local)}@example.com"


@pytest.fixture(scope="session")
def client():
    app.state.limiter.enabled = False
    with TestClient(app) as c:
        yield c


class ApiUser:
    def __init__(self, email, username, password, access_token, refresh_token):
        self.email = email
        self.username = username
        self.password = password
        self.access_token = access_token
        self.refresh_token = refresh_token

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}


def register_user(client, username=None, email=None, password="Str0ngPass!9"):
    username = username or _unique("user")
    email = email or _unique_email(username)
    res = client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    return ApiUser(
        email=email,
        username=username,
        password=password,
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
    )


def upload_csv(client, user, content=CSV_CONTENT, name=None):
    name = name or _unique("ds")
    files = {"file": ("data.csv", io.BytesIO(content.encode()), "text/csv")}
    data = {"name": name}
    res = client.post("/api/data/upload", files=files, data=data, headers=user.headers)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def user(client):
    return register_user(client)


@pytest.fixture
def dataset(client, user):
    return upload_csv(client, user)


@pytest.fixture
def second_user(client):
    return register_user(client)
