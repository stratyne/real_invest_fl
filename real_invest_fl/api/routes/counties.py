"""
Counties route — returns active counties the current user is authorised to access.

GET /counties
    Superusers: all active counties.
    Regular users: active counties where a user_county_access row exists.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import get_current_user, get_db
from real_invest_fl.db.models.county import County
from real_invest_fl.db.models.user import User
from real_invest_fl.db.models.user_county_access import UserCountyAccess

router = APIRouter(prefix="/counties", tags=["counties"])


# ── Response schema ──────────────────────────────────────────────────────

class CountyResponse(BaseModel):
    county_fips: str
    county_name: str
    state_abbr: str
    dor_county_no: int
    poc_county: bool
    nal_last_ingested_at: datetime | None
    cama_last_ingested_at: datetime | None

    model_config = {"from_attributes": True}


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[CountyResponse])
async def list_counties(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CountyResponse]:
    """Return active counties the current user is authorised to access.

    Superusers receive all active counties.
    Regular users receive only counties with a user_county_access row.
    """
    if current_user.is_superuser:
        result = await db.execute(
            select(County)
            .where(County.active.is_(True))
            .order_by(County.county_name)
        )
        counties = result.scalars().all()
    else:
        result = await db.execute(
            select(County)
            .join(
                UserCountyAccess,
                UserCountyAccess.county_fips == County.county_fips,
            )
            .where(
                County.active.is_(True),
                UserCountyAccess.user_id == current_user.id,
            )
            .order_by(County.county_name)
        )
        counties = result.scalars().all()

    return [CountyResponse.model_validate(c) for c in counties]
