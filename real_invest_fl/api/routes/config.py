"""
Config routes — county metadata management. Superuser only.

GET   /config/counties              — list all counties including inactive.
PATCH /config/counties/{county_fips} — update county metadata.

All routes in this module require is_superuser. Regular users receive 403.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import get_current_user, get_db
from real_invest_fl.db.models.county import County
from real_invest_fl.db.models.user import User

router = APIRouter(prefix="/config", tags=["config"])


# ── Schemas ──────────────────────────────────────────────────────────────

class CountyAdminResponse(BaseModel):
    county_fips: str
    county_name: str
    state_abbr: str
    dor_county_no: int
    active: bool
    poc_county: bool
    nal_last_ingested_at: datetime | None
    sdf_last_ingested_at: datetime | None
    cama_last_ingested_at: datetime | None
    nal_file_path: str | None
    sdf_file_path: str | None
    cama_file_path: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CountyUpdateRequest(BaseModel):
    active: bool | None = None
    poc_county: bool | None = None
    nal_file_path: str | None = None
    sdf_file_path: str | None = None
    cama_file_path: str | None = None


# ── Superuser guard ──────────────────────────────────────────────────────

def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    """Raise 403 for any non-superuser. Returns user on success."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("/counties", response_model=list[CountyAdminResponse])
async def list_all_counties(
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[CountyAdminResponse]:
    """Return all counties including inactive. Superuser only."""
    result = await db.execute(
        select(County).order_by(County.county_name)
    )
    counties = result.scalars().all()
    return [CountyAdminResponse.model_validate(c) for c in counties]


@router.patch(
    "/counties/{county_fips}",
    response_model=CountyAdminResponse,
)
async def update_county(
    county_fips: str,
    body: CountyUpdateRequest,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> CountyAdminResponse:
    """Update county metadata. Superuser only.

    Only fields present in the request body are updated — omitted fields
    are left unchanged. county_fips, county_name, dor_county_no, and
    state_abbr are immutable via this endpoint.
    """
    result = await db.execute(
        select(County).where(County.county_fips == county_fips)
    )
    county: County | None = result.scalar_one_or_none()

    if county is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"County {county_fips} not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(county, field, value)

    await db.flush()
    await db.refresh(county)
    return CountyAdminResponse.model_validate(county)
