"""
Shared FastAPI dependencies — DB session, auth, county access enforcement.

get_current_user:  validates JWT, returns User ORM object.
county_access():   factory — returns a dependency that enforces
                   user_county_access membership for a county-scoped route.
                   Superusers bypass the check entirely.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status
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


def county_access(fips_param: str = "county_fips"):
    """Return a FastAPI dependency that enforces county access for a route.

    Extracts county_fips from the path parameter named by fips_param,
    checks user_county_access, and returns the validated fips string.
    Superusers bypass the access check entirely.

    Args:
        fips_param: Name of the path parameter carrying the county FIPS.
                    Defaults to 'county_fips'. Override only if the route
                    uses a different path parameter name.

    Usage:
        @router.get("/{county_fips}/properties")
        async def list_properties(
            county_fips: str = Depends(county_access()),
            db: AsyncSession = Depends(get_db),
        ) -> ...:
            ...

    Routes that also need the current user must declare it separately:
        current_user: User = Depends(get_current_user)
    """
    async def _dep(
        county_fips: str = Path(..., alias=fips_param),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> str:
        if current_user.is_superuser:
            return county_fips

        result = await db.execute(
            select(UserCountyAccess).where(
                UserCountyAccess.user_id == current_user.id,
                UserCountyAccess.county_fips == county_fips,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access to county {county_fips} not authorised",
            )

        return county_fips

    return _dep


# Re-export get_db for call sites that import everything from deps
from real_invest_fl.db.session import get_db as get_db  # noqa: F811, E402
