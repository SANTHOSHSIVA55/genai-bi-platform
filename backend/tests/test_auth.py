from auth import (
    create_email_verification_token,
    create_password_reset_token,
)
from database import SessionLocal
from models import User
from conftest import _unique, _unique_email, register_user


def _get_user_by_email(email):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first()
    finally:
        db.close()


class TestRegister:
    def test_success_returns_tokens_and_user(self, client):
        res = client.post(
            "/api/auth/register",
            json={"email": _unique_email("a"), "username": _unique("user"), "password": "Str0ngPass!9"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["user"]["email"]
        assert body["user"]["role"] == "user"
        assert "hashed_password" not in body["user"]

    def test_duplicate_email(self, client, user):
        res = client.post(
            "/api/auth/register",
            json={"email": user.email, "username": _unique("user"), "password": "Str0ngPass!9"},
        )
        assert res.status_code == 400

    def test_duplicate_username(self, client, user):
        res = client.post(
            "/api/auth/register",
            json={"email": _unique_email("a"), "username": user.username, "password": "Str0ngPass!9"},
        )
        assert res.status_code == 400

    def test_weak_password_rejected(self, client):
        res = client.post(
            "/api/auth/register",
            json={"email": _unique_email("a"), "username": _unique("user"), "password": "short1"},
        )
        assert res.status_code == 422

    def test_password_without_upper_rejected(self, client):
        res = client.post(
            "/api/auth/register",
            json={"email": _unique_email("a"), "username": _unique("user"), "password": "lowercase123"},
        )
        assert res.status_code == 422

    def test_password_without_digit_rejected(self, client):
        res = client.post(
            "/api/auth/register",
            json={"email": _unique_email("a"), "username": _unique("user"), "password": "OnlyLetters"},
        )
        assert res.status_code == 422

    def test_invalid_email_rejected(self, client):
        res = client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "username": _unique("user"), "password": "Str0ngPass!9"},
        )
        assert res.status_code == 422

    def test_invalid_username_rejected(self, client):
        res = client.post(
            "/api/auth/register",
            json={"email": _unique_email("a"), "username": "bad username!!", "password": "Str0ngPass!9"},
        )
        assert res.status_code == 422


class TestLogin:
    def test_success(self, client, user):
        res = client.post("/api/auth/login", json={"email": user.email, "password": user.password})
        assert res.status_code == 200
        assert res.json()["access_token"]

    def test_wrong_password(self, client, user):
        res = client.post("/api/auth/login", json={"email": user.email, "password": "WrongPass123"})
        assert res.status_code == 401

    def test_unknown_email(self, client):
        res = client.post(
            "/api/auth/login",
            json={"email": _unique_email("ghost"), "password": "WrongPass123"},
        )
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid email or password"

    def test_disabled_account(self, client, user):
        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.email == user.email).first()
            db_user.is_active = False
            db.commit()
        finally:
            db.close()
        res = client.post("/api/auth/login", json={"email": user.email, "password": user.password})
        assert res.status_code == 403


class TestMe:
    def test_requires_auth(self, client):
        res = client.get("/api/auth/me")
        assert res.status_code == 401

    def test_valid_token(self, client, user):
        res = client.get("/api/auth/me", headers=user.headers)
        assert res.status_code == 200
        assert res.json()["email"] == user.email

    def test_garbage_token(self, client):
        res = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert res.status_code == 401


class TestRefresh:
    def test_rotation_issues_new_pair(self, client, user):
        res = client.post("/api/auth/refresh", json={"refresh_token": user.refresh_token})
        assert res.status_code == 200
        body = res.json()
        # Access JWTs are deterministic within the same second (no jti); the
        # refresh token must rotate and the new access token must be usable.
        assert body["refresh_token"] != user.refresh_token
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200
        assert me.json()["email"] == user.email

    def test_old_refresh_rejected_after_rotation(self, client, user):
        res = client.post("/api/auth/refresh", json={"refresh_token": user.refresh_token})
        assert res.status_code == 200
        res2 = client.post("/api/auth/refresh", json={"refresh_token": user.refresh_token})
        assert res2.status_code == 401

    def test_garbage_refresh(self, client):
        res = client.post("/api/auth/refresh", json={"refresh_token": "garbage-token-value"})
        assert res.status_code == 401


class TestLogout:
    def test_revokes_all_refresh_tokens(self, client, user):
        res = client.post(
            "/api/auth/logout", json={"refresh_token": user.refresh_token}, headers=user.headers
        )
        assert res.status_code == 200
        res2 = client.post("/api/auth/refresh", json={"refresh_token": user.refresh_token})
        assert res2.status_code == 401


class TestEmailVerification:
    def test_invalid_token_fails(self, client):
        res = client.post("/api/auth/verify-email", json={"token": "garbage-token"})
        assert res.status_code in (400, 401)

    def test_valid_token_verifies(self, client, user):
        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.email == user.email).first()
            token = create_email_verification_token(db_user, db)
        finally:
            db.close()
        res = client.post("/api/auth/verify-email", json={"token": token})
        assert res.status_code == 200
        assert _get_user_by_email(user.email).is_email_verified


class TestPasswordReset:
    def test_forgot_returns_generic_message(self, client, user):
        res = client.post("/api/auth/forgot-password", json={"email": user.email})
        assert res.status_code == 200

    def test_forgot_does_not_leak_unknown_email(self, client):
        res = client.post(
            "/api/auth/forgot-password", json={"email": _unique_email("ghost")}
        )
        assert res.status_code == 200

    def test_reset_with_valid_token(self, client, user):
        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.email == user.email).first()
            token = create_password_reset_token(db_user, db)
        finally:
            db.close()
        new_password = "NewStr0ngPass1"
        res = client.post(
            "/api/auth/reset-password", json={"token": token, "password": new_password}
        )
        assert res.status_code == 200

        res_old = client.post("/api/auth/login", json={"email": user.email, "password": user.password})
        assert res_old.status_code == 401
        res_new = client.post("/api/auth/login", json={"email": user.email, "password": new_password})
        assert res_new.status_code == 200

    def test_reset_with_garbage_token(self, client):
        res = client.post(
            "/api/auth/reset-password", json={"token": "garbage-token", "password": "NewStr0ngPass1"}
        )
        assert res.status_code in (400, 401)


class TestResendVerification:
    def test_known_email(self, client, user):
        res = client.post("/api/auth/resend-verification", json={"email": user.email})
        assert res.status_code == 200

    def test_unknown_email_generic(self, client):
        res = client.post(
            "/api/auth/resend-verification", json={"email": _unique_email("ghost")}
        )
        assert res.status_code == 200

