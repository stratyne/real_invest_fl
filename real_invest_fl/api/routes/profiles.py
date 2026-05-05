"""
Filter profile routes — profile management for county-scoped investment filters.

GET    /{county_fips}/profiles                        — list system + own profiles.
POST   /{county_fips}/profiles                        — create a new user-owned profile.
POST   /{county_fips}/profiles/{profile_id}/clone     — clone any visible profile.
PATCH  /{county_fips}/profiles/{profile_id}           — update a user-owned profile.
DELETE /{county_fips}/profiles/{profile_id}           — delete a user-owned profile.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import county_access, get_current_user, get_db
from real_invest_fl.db.models.filter_profile import FilterProfile
from real_invest_fl.db.models.user import User

router = APIRouter(prefix="/{county_fips}/profiles", tags=["profiles"])


# ── Schemas ──────────────────────────────────────────────────────────────

class FilterProfileResponse(BaseModel):
    id: int
    profile_name: str
    county_fips: str
    description: str | None
    is_active: bool
    version: int
    user_id: int | None
    filter_criteria: dict
    rehab_cost_per_sqft: float
    min_comp_sales_for_arv: int
    comp_radius_miles: float
    comp_year_built_tolerance: int
    listing_type_priority: dict
    deal_score_weights: dict
    allow_automated_outreach: bool
    max_outreach_attempts: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FilterProfileCreateRequest(BaseModel):
    profile_name: str
    description: str | None = None
    is_active: bool = True
    filter_criteria: dict
    rehab_cost_per_sqft: float = 22.00
    min_comp_sales_for_arv: int = 3
    comp_radius_miles: float = 1.0
    comp_year_built_tolerance: int = 15
    listing_type_priority: dict = {}
    deal_score_weights: dict = {}
    allow_automated_outreach: bool = False
    max_outreach_attempts: int = 3


class FilterProfileUpdateRequest(BaseModel):
    profile_name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    filter_criteria: dict | None = None
    rehab_cost_per_sqft: float | None = None
    min_comp_sales_for_arv: int | None = None
    comp_radius_miles: float | None = None
    comp_year_built_tolerance: int | None = None
    listing_type_priority: dict | None = None
    deal_score_weights: dict | None = None
    allow_automated_outreach: bool | None = None
    max_outreach_attempts: int | None = None


class CloneProfileRequest(BaseModel):
    profile_name: str


# ── Helpers ──────────────────────────────────────────────────────────────

async def _get_visible_profile(
    profile_id: int,
    county_fips: str,
    current_user: User,
    db: AsyncSession,
) -> FilterProfile:
    """Return a profile visible to the user — system or own.

    Raises 404 if not found or not visible.
    A profile is visible if it is a system profile (user_id IS NULL)
    or owned by the current user.
    Superusers can see all profiles in the county.
    """
    stmt = select(FilterProfile).where(
        FilterProfile.id == profile_id,
        FilterProfile.county_fips == county_fips,
    )
    result = await db.execute(stmt)
    profile: FilterProfile | None = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter profile {profile_id} not found in county {county_fips}",
        )

    if not current_user.is_superuser:
        if profile.user_id is not None and profile.user_id != current_user.id:
            # Exists but belongs to another user — return 404, not 403,
            # to avoid leaking the existence of other users' profiles.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Filter profile {profile_id} not found in county {county_fips}",
            )

    return profile


async def _get_owned_profile(
    profile_id: int,
    county_fips: str,
    current_user: User,
    db: AsyncSession,
) -> FilterProfile:
    """Return a profile the user owns and may mutate.

    Raises 404 if not found.
    Raises 403 if the profile is a system profile.
    Raises 403 if the profile belongs to another user.
    Superusers may mutate any non-system profile.
    """
    result = await db.execute(
        select(FilterProfile).where(
            FilterProfile.id == profile_id,
            FilterProfile.county_fips == county_fips,
        )
    )
    profile: FilterProfile | None = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter profile {profile_id} not found in county {county_fips}",
        )

    if profile.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System profiles cannot be modified or deleted",
        )

    if not current_user.is_superuser and profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this profile",
        )

    return profile


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[FilterProfileResponse])
async def list_profiles(
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FilterProfileResponse]:
    """Return all visible profiles for the county.

    Includes system profiles (user_id IS NULL) and the current user's
    own profiles. Superusers see all profiles in the county.
    Results ordered by user_id nulls first (system profiles first),
    then profile_name.
    """
    if current_user.is_superuser:
        stmt = (
            select(FilterProfile)
            .where(FilterProfile.county_fips == county_fips)
            .order_by(FilterProfile.user_id.nullsfirst(), FilterProfile.profile_name)
        )
    else:
        stmt = (
            select(FilterProfile)
            .where(
                FilterProfile.county_fips == county_fips,
                (FilterProfile.user_id.is_(None))
                | (FilterProfile.user_id == current_user.id),
            )
            .order_by(FilterProfile.user_id.nullsfirst(), FilterProfile.profile_name)
        )

    result = await db.execute(stmt)
    profiles = result.scalars().all()
    return [FilterProfileResponse.model_validate(p) for p in profiles]


@router.post("", response_model=FilterProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    body: FilterProfileCreateRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> FilterProfileResponse:
    """Create a new user-owned filter profile.

    user_id is set server-side to current_user.id — never accepted
    from the request body. version starts at 1.
    """
    profile = FilterProfile(
        profile_name=body.profile_name,
        county_fips=county_fips,
        description=body.description,
        is_active=body.is_active,
        version=1,
        user_id=current_user.id,
        filter_criteria=body.filter_criteria,
        rehab_cost_per_sqft=body.rehab_cost_per_sqft,
        min_comp_sales_for_arv=body.min_comp_sales_for_arv,
        comp_radius_miles=body.comp_radius_miles,
        comp_year_built_tolerance=body.comp_year_built_tolerance,
        listing_type_priority=body.listing_type_priority,
        deal_score_weights=body.deal_score_weights,
        allow_automated_outreach=body.allow_automated_outreach,
        max_outreach_attempts=body.max_outreach_attempts,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return FilterProfileResponse.model_validate(profile)


@router.post(
    "/{profile_id}/clone",
    response_model=FilterProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_profile(
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    profile_id: int = Path(..., description="ID of the profile to clone"),
    body: CloneProfileRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> FilterProfileResponse:
    """Clone any visible profile into a new user-owned profile.

    The source profile may be a system profile or the user's own.
    The clone is always user-owned (user_id = current_user.id).
    version resets to 1 on the clone.
    """
    source = await _get_visible_profile(profile_id, county_fips, current_user, db)

    clone = FilterProfile(
        profile_name=body.profile_name,
        county_fips=county_fips,
        description=source.description,
        is_active=True,
        version=1,
        user_id=current_user.id,
        filter_criteria=source.filter_criteria,
        rehab_cost_per_sqft=source.rehab_cost_per_sqft,
        min_comp_sales_for_arv=source.min_comp_sales_for_arv,
        comp_radius_miles=source.comp_radius_miles,
        comp_year_built_tolerance=source.comp_year_built_tolerance,
        listing_type_priority=source.listing_type_priority,
        deal_score_weights=source.deal_score_weights,
        allow_automated_outreach=source.allow_automated_outreach,
        max_outreach_attempts=source.max_outreach_attempts,
    )
    db.add(clone)
    await db.flush()
    await db.refresh(clone)
    return FilterProfileResponse.model_validate(clone)


@router.patch("/{profile_id}", response_model=FilterProfileResponse)
async def update_profile(
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    profile_id: int = Path(..., description="ID of the profile to update"),
    body: FilterProfileUpdateRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> FilterProfileResponse:
    """Update a user-owned filter profile.

    Only fields present in the request body are updated.
    version is incremented on every successful update.
    System profiles and profiles owned by other users return 403.
    """
    profile = await _get_owned_profile(profile_id, county_fips, current_user, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    profile.version += 1

    await db.flush()
    await db.refresh(profile)
    return FilterProfileResponse.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    county_fips: str = Depends(county_access()),
    current_user: User = Depends(get_current_user),
    profile_id: int = Path(..., description="ID of the profile to delete"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user-owned filter profile.

    System profiles and profiles owned by other users return 403.
    Superusers may delete any non-system profile.
    Cascades to listing_scores rows via FK ON DELETE CASCADE.
    """
    profile = await _get_owned_profile(profile_id, county_fips, current_user, db)
    await db.delete(profile)
    await db.flush()
