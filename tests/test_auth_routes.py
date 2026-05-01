"""
Integration tests for auth routes using FastAPI TestClient.
DB is mocked via dependency overrides — no live database required.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from real_invest_fl.api.main import app
from real_invest_fl.api.deps import get_db, get_current_user
from real_invest_fl.auth.passwords import hash_password
from real_invest_fl.auth.tokens import create_access_token
from real_invest_fl.db.models.user import User


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_user(
    id: int = 1,
    email: str = "admin@example.com",
    password: str = "correct-password-123",
    is_active: bool = True,
    is_superuser: bool = False,
) -> User:
    u = User()
    u.id = id
    u.email = email
    u.hashed_password = hash_password(password)
    u.full_name = "Test User"
    u.is_active = is_active
    u.is_superuser = is_superuser
    return u


def _db_override_returning(user: User | None):
    """Return an async generator that yields a mock session.

    The mock session's execute() returns a result whose
    scalar_one_or_none() returns the given user.
    """
    async def _override():
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session = AsyncMock()
        session.execute.return_value = mock_result
        yield session
    return _override


# ── Login (POST /auth/token) tests ───────────────────────────────────────

class TestLoginRoute:
    def test_valid_credentials_return_token(self):
        user = _make_user(password="correct-password-123")
        app.dependency_overrides[get_db] = _db_override_returning(user)
        try:
            client = TestClient(app)
            resp = client.post(
                "/auth/token",
                data={"username": "admin@example.com", "password": "correct-password-123"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "access_token" in body
            assert body["token_type"] == "bearer"
            assert len(body["access_token"]) > 20
        finally:
            app.dependency_overrides.clear()

    def test_wrong_password_returns_401(self):
        user = _make_user(password="correct-password-123")
        app.dependency_overrides[get_db] = _db_override_returning(user)
        try:
            client = TestClient(app)
            resp = client.post(
                "/auth/token",
                data={"username": "admin@example.com", "password": "wrong-password"},
            )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_unknown_email_returns_401(self):
        app.dependency_overrides[get_db] = _db_override_returning(None)
        try:
            client = TestClient(app)
            resp = client.post(
                "/auth/token",
                data={"username": "ghost@example.com", "password": "anything"},
            )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    def test_inactive_user_returns_401(self):
        user = _make_user(password="correct-password-123", is_active=False)
        app.dependency_overrides[get_db] = _db_override_returning(user)
        try:
            client = TestClient(app)
            resp = client.post(
                "/auth/token",
                data={"username": "admin@example.com", "password": "correct-password-123"},
            )
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


# ── Profile (GET /auth/me) tests ─────────────────────────────────────────

class TestMeRoute:
    def test_valid_token_returns_profile(self):
        user = _make_user()
        token = create_access_token(user_id=user.id, email=user.email)

        async def _user_override():
            return user

        app.dependency_overrides[get_current_user] = _user_override
        try:
            client = TestClient(app)
            resp = client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == 1
            assert body["email"] == "admin@example.com"
            assert body["is_active"] is True
            assert body["is_superuser"] is False
        finally:
            app.dependency_overrides.clear()

    def test_no_token_returns_401(self):
        client = TestClient(app)
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        client = TestClient(app)
        resp = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer this.is.not.valid"},
        )
        assert resp.status_code == 401


# ── Health check still passes after router wiring ────────────────────────

class TestHealthAfterWiring:
    def test_health_returns_ok(self):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── UISession no longer importable ───────────────────────────────────────

class TestUISessionRetired:
    def test_ui_session_not_in_models(self):
        import real_invest_fl.db.models as models_pkg
        assert not hasattr(models_pkg, "UISession"), (
            "UISession should have been removed from models/__init__.py"
        )
