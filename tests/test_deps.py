"""
Unit tests for FastAPI dependency functions.
All DB interaction is mocked — no live database required.
"""
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from real_invest_fl.api.deps import get_current_user, require_county_access
from real_invest_fl.auth.tokens import create_access_token
from real_invest_fl.db.models.user import User
from real_invest_fl.db.models.user_county_access import UserCountyAccess


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_user(id: int = 1, is_active: bool = True, is_superuser: bool = False) -> User:
    u = User()
    u.id = id
    u.email = "test@example.com"
    u.hashed_password = "irrelevant"
    u.is_active = is_active
    u.is_superuser = is_superuser
    return u


def _mock_db_returning(obj) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    session = AsyncMock()
    session.execute.return_value = result
    return session


# ── get_current_user ─────────────────────────────────────────────────────

class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        user = _make_user()
        token = create_access_token(user_id=1, email="test@example.com")
        db = _mock_db_returning(user)
        result = await get_current_user(token=token, db=db)
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone
        from config.settings import settings

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "1", "email": "a@b.com", "type": "access",
            "iat": now, "exp": now - timedelta(seconds=1),
        }
        expired_token = pyjwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        db = _mock_db_returning(None)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=expired_token, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_token_raises_401(self):
        db = _mock_db_returning(None)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="garbage.token.value", db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_raises_401(self):
        user = _make_user(is_active=False)
        token = create_access_token(user_id=1, email="test@example.com")
        db = _mock_db_returning(user)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_in_db_raises_401(self):
        token = create_access_token(user_id=999, email="ghost@example.com")
        db = _mock_db_returning(None)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token, db=db)
        assert exc_info.value.status_code == 401


# ── require_county_access ────────────────────────────────────────────────

class TestRequireCountyAccess:
    @pytest.mark.asyncio
    async def test_superuser_bypasses_check(self):
        user = _make_user(is_superuser=True)
        db = _mock_db_returning(None)  # Would 403 a regular user
        result = await require_county_access(
            county_fips="12033", current_user=user, db=db
        )
        assert result == "12033"

    @pytest.mark.asyncio
    async def test_user_with_access_returns_fips(self):
        user = _make_user()
        access_row = UserCountyAccess()
        access_row.user_id = user.id
        access_row.county_fips = "12033"
        db = _mock_db_returning(access_row)
        result = await require_county_access(
            county_fips="12033", current_user=user, db=db
        )
        assert result == "12033"

    @pytest.mark.asyncio
    async def test_user_without_access_raises_403(self):
        user = _make_user()
        db = _mock_db_returning(None)  # No access row
        with pytest.raises(HTTPException) as exc_info:
            await require_county_access(
                county_fips="12033", current_user=user, db=db
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_superuser_with_different_fips_still_passes(self):
        user = _make_user(is_superuser=True)
        db = _mock_db_returning(None)
        # Superuser should pass even for a county they have no explicit row for
        result = await require_county_access(
            county_fips="12113", current_user=user, db=db
        )
        assert result == "12113"
