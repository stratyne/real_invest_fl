"""
Shared FastAPI dependencies — DB session, auth, county access enforcement.

get_current_user: validates JWT, returns User ORM object.
require_county_access: enforces user_county_access membership.
    Superusers bypass the check entirely.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.auth.tokens import TokenError, decode_access_token, extract_user_id
from real_invest_fl.db.models.user import User
from real_invest_fl.db.models.user_county_access import UserCountyAccess
from real_invest_fl.db.session import get_db

# Token URL matches the login endpoint wired in auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode JWT and return the corresponding User row.

    Raises 401 on any token problem or if the user does not exist
    or is inactive.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = extract_user_id(payload)
    except TokenError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exc

    return user


async def require_county_access(
    county_fips: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Verify the current user is authorised to access county_fips.

    Superusers bypass the check entirely.
    Returns county_fips on success for use by the calling route.
    Raises 403 if access is denied.

    Note: county_fips must be passed explicitly by the route — this
    dependency does not extract it from the path automatically.
    Typical route usage:
        fips = await require_county_access("12033", current_user, db)
    Or as a FastAPI Depends chain in a sub-dependency per route.
    """
    if current_user.is_superuser:
        return county_fips

    result = await db.execute(
        select(UserCountyAccess).where(
            UserCountyAccess.user_id == current_user.id,
            UserCountyAccess.county_fips == county_fips,
        )
    )
    access_row = result.scalar_one_or_none()

    if access_row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access to county {county_fips} not authorised",
        )

    return county_fips


# Re-export get_db for call sites that import everything from deps
from real_invest_fl.db.session import get_db as get_db  # noqa: F811, E402
