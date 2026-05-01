"""JWT creation and decode utilities.

sub claim: users.id as string — the single canonical subject identity.
email claim: included as a display hint only. Never used for lookups.
type claim: 'access' — reserved for future refresh token differentiation.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from config.settings import settings


class TokenError(Exception):
    """Raised when a token cannot be decoded or is structurally invalid."""


def create_access_token(user_id: int, email: str) -> str:
    """Encode a signed JWT access token.

    Args:
        user_id: The users.id — stored as str in sub.
        email:   Stored as display hint only.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub":   str(user_id),
        "email": email,
        "type":  "access",
        "iat":   now,
        "exp":   expire,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Returns:
        The decoded payload dict.

    Raises:
        TokenError: on expiry, invalid signature, missing sub, or wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError:
        raise TokenError("Token has expired")
    except InvalidTokenError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc

    if payload.get("type") != "access":
        raise TokenError("Token type is not 'access'")

    if not payload.get("sub"):
        raise TokenError("Token missing 'sub' claim")

    return payload


def extract_user_id(payload: dict[str, Any]) -> int:
    """Extract and cast the sub claim to int.

    Raises:
        TokenError: if sub is missing or non-numeric.
    """
    sub = payload.get("sub")
    if not sub:
        raise TokenError("Missing 'sub' claim")
    try:
        return int(sub)
    except (ValueError, TypeError):
        raise TokenError(f"'sub' claim is not a valid integer: {sub!r}")
