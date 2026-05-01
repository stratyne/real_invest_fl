"""
Unit tests for auth utilities — passwords.py and tokens.py.
No database required. All tests are pure function calls.
"""
import time
from datetime import timedelta
from unittest.mock import patch

import pytest

from real_invest_fl.auth.passwords import hash_password, verify_password
from real_invest_fl.auth.tokens import (
    TokenError,
    create_access_token,
    decode_access_token,
    extract_user_id,
)


# ── Password tests ───────────────────────────────────────────────────────

class TestPasswords:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("supersecret")
        assert hashed != "supersecret"

    def test_verify_correct_password(self):
        hashed = hash_password("correct-horse-battery")
        assert verify_password("correct-horse-battery", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct-horse-battery")
        assert verify_password("wrong-password", hashed) is False

    def test_verify_empty_string_fails(self):
        hashed = hash_password("notempty")
        assert verify_password("", hashed) is False

    def test_two_hashes_of_same_password_differ(self):
        # bcrypt uses random salt — same input must not produce same hash
        hashed1 = hash_password("same-password")
        hashed2 = hash_password("same-password")
        assert hashed1 != hashed2
        # But both must verify correctly
        assert verify_password("same-password", hashed1) is True
        assert verify_password("same-password", hashed2) is True


# ── Token tests ──────────────────────────────────────────────────────────

class TestTokens:
    def test_create_and_decode_roundtrip(self):
        token = create_access_token(user_id=42, email="test@example.com")
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_extract_user_id_returns_int(self):
        token = create_access_token(user_id=99, email="x@x.com")
        payload = decode_access_token(token)
        uid = extract_user_id(payload)
        assert uid == 99
        assert isinstance(uid, int)

    def test_expired_token_raises_token_error(self):
        # Patch timedelta so the token expires immediately
        import jwt as pyjwt
        from config.settings import settings
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub":   "1",
            "email": "a@b.com",
            "type":  "access",
            "iat":   now,
            "exp":   now - timedelta(seconds=1),  # already expired
        }
        token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(TokenError, match="expired"):
            decode_access_token(token)

    def test_wrong_algorithm_raises_token_error(self):
        import jwt as pyjwt
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "1", "email": "a@b.com", "type": "access",
            "iat": now, "exp": now + timedelta(minutes=5),
        }
        # Sign with a different secret
        token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(TokenError):
            decode_access_token(token)

    def test_missing_sub_raises_token_error(self):
        import jwt as pyjwt
        from config.settings import settings
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        payload = {
            "email": "a@b.com", "type": "access",
            "iat": now, "exp": now + timedelta(minutes=5),
        }
        token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(TokenError, match="sub"):
            decode_access_token(token)

    def test_wrong_type_claim_raises_token_error(self):
        import jwt as pyjwt
        from config.settings import settings
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": "1", "email": "a@b.com", "type": "refresh",
            "iat": now, "exp": now + timedelta(minutes=5),
        }
        token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(TokenError, match="type"):
            decode_access_token(token)

    def test_extract_user_id_non_numeric_raises(self):
        payload = {"sub": "not-a-number"}
        with pytest.raises(TokenError, match="integer"):
            extract_user_id(payload)

    def test_extract_user_id_missing_raises(self):
        with pytest.raises(TokenError, match="Missing"):
            extract_user_id({})
