"""
Auth routes — login and current-user profile only.

POST /auth/token  — OAuth2 password flow login, returns access token.
GET  /auth/me     — Returns the current authenticated user's profile.
PATCH /auth/me    — Updates full_name, calendar_link, and/or password.

Deferred to Phase 4: password reset, email verification,
user self-registration, user management endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.auth.passwords import hash_password, verify_password
from real_invest_fl.auth.tokens import create_access_token
from real_invest_fl.api.deps import get_current_user, get_db
from real_invest_fl.db.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Response / request schemas ────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: int
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool
    calendar_link: str | None
    created_at: str

    model_config = {"from_attributes": True}

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_created_at(cls, v: object) -> str:
        """Serialise datetime to ISO 8601 string for JSON transport."""
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


class UserUpdate(BaseModel):
    """Partial update — only supplied fields are written.

    All fields are optional. An empty payload is a no-op.
    email, is_active, and is_superuser are not user-editable via this route.
    """
    full_name: str | None = None
    calendar_link: str | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 12:
            raise ValueError("Password must be at least 12 characters.")
        return v

    @field_validator("calendar_link")
    @classmethod
    def _validate_calendar_link(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 1000:
            raise ValueError("calendar_link must be 1000 characters or fewer.")
        return v

    @field_validator("full_name")
    @classmethod
    def _validate_full_name(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 200:
            raise ValueError("full_name must be 200 characters or fewer.")
        return v


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email + password, return a signed JWT access token.

    form_data.username is treated as the user's email address
    (OAuth2 spec uses 'username' as the field name).
    """
    result = await db.execute(
        select(User).where(User.email == form_data.username)
    )
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user_id=user.id, email=user.email)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserProfile)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserProfile:
    """Return the authenticated user's profile."""
    return UserProfile.model_validate(current_user)


@router.patch("/me", response_model=UserProfile)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Partially update the authenticated user's own profile.

    Only full_name, calendar_link, and password may be changed here.
    Supplying a field as null explicitly clears it (full_name, calendar_link).
    Omitting a field entirely leaves it unchanged.
    An empty payload body is a no-op — current profile is returned unchanged.
    """
    updated_fields: list[str] = []

    # full_name: explicit null clears the field; supplied string sets it
    if "full_name" in payload.model_fields_set:
        current_user.full_name = payload.full_name
        updated_fields.append("full_name")

    # calendar_link: explicit null clears the field; supplied string sets it
    if "calendar_link" in payload.model_fields_set:
        current_user.calendar_link = payload.calendar_link
        updated_fields.append("calendar_link")

    # password: hash and store; immediately discard plaintext
    if "password" in payload.model_fields_set and payload.password is not None:
        current_user.hashed_password = hash_password(payload.password)
        payload.password = None  # discard plaintext from memory
        updated_fields.append("password")

    if updated_fields:
        await db.flush()
        await db.refresh(current_user)
        print(f"[auth] User {current_user.id} updated fields: {updated_fields}")

    return UserProfile.model_validate(current_user)
