"""
Auth routes — login and current-user profile only.

POST /auth/token  — OAuth2 password flow login, returns access token.
GET  /auth/me     — Returns the current authenticated user's profile.

Deferred to Phase 4: password reset, email verification,
user self-registration, user management endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.auth.passwords import verify_password
from real_invest_fl.auth.tokens import create_access_token
from real_invest_fl.api.deps import get_current_user, get_db
from real_invest_fl.db.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Response schemas ─────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: int
    email: str
    full_name: str | None
    is_active: bool
    is_superuser: bool

    model_config = {"from_attributes": True}


# ── Routes ───────────────────────────────────────────────────────────────

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
async def get_me(current_user: User = Depends(get_current_user)) -> UserProfile:
    """Return the authenticated user's profile."""
    return UserProfile.model_validate(current_user)
