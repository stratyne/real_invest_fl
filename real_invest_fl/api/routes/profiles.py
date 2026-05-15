"""
Filter profile routes — profile management for multi-county investment filters.

GET    /{county_fips}/profiles                        — list system + own profiles
       visible to the user for the given county.
POST   /{county_fips}/profiles                        — create a new user-owned profile.
POST   /{county_fips}/profiles/{profile_id}/clone     — clone any visible profile.
PATCH  /{county_fips}/profiles/{profile_id}           — update a user-owned profile.
DELETE /{county_fips}/profiles/{profile_id}           — delete a user-owned profile.
PATCH  /{county_fips}/profiles/{profile_id}/favorite  — toggle is_favorite on
       user_profile_prefs for (current_user.id, profile_id).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import get_current_user, get_db
from real_invest_fl.db.models.filter_profile import FilterProfile
from real_invest_fl.db.models.user import User
from real_invest_fl.db.models.user_profile_prefs import UserProfilePrefs

router = APIRouter(prefix="/profiles", tags=["profiles"])


# ── Schemas ──────────────────────────────────────────────────────────────

class FilterProfileResponse(BaseModel):
    id: int
    profile_name: str
    county_fips: list[str]
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
    county_fips: list[str]
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
    county_fips: list[str] | None = None
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
    county_fips: list[str] | None = None


class ToggleFavoriteResponse(BaseModel):
    is_favorite: bool


# ── Access validation helpers ─────────────────────────────────────────────

def _assert_county_access(
    requested_fips: list[str],
    accessible_fips: set[str],
    is_superuser: bool,
) -> None:
    """Raise 403 if the user does not have access to all requested counties.

    Superusers bypass this check entirely.
    """
    if is_superuser:
        return
    denied = [f for f in requested_fips if f not in accessible_fips]
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied for counties: {', '.join(denied)}",
        )


async def _get_accessible_fips(
    current_user: User,
    db: AsyncSession,
) -> set[str]:
    """Return the set of county FIPS the current user can access.

    Superusers get an empty set — callers must check is_superuser first
    and bypass this result entirely.
    """
    from real_invest_fl.db.models.user_county_access import UserCountyAccess
    result = await db.execute(
        select(UserCountyAccess.county_fips).where(
            UserCountyAccess.user_id == current_user.id
        )
    )
    return {row for row in result.scalars().all()}


# ── Profile visibility helpers ────────────────────────────────────────────

async def _get_visible_profile(
    profile_id: int,
    current_user: User,
    db: AsyncSession,
) -> FilterProfile:
    """Return a profile visible to the user.

    A profile is visible if it is a system profile (user_id IS NULL) or
    owned by the current user, and the user has access to all counties in
    the profile. Superusers see all profiles.
    """
    result = await db.execute(
        select(FilterProfile).where(
            FilterProfile.id == profile_id,
        )
    )
    profile: FilterProfile | None = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter profile {profile_id} not found",
        )

    if current_user.is_superuser:
        return profile

    if profile.user_id is not None and profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter profile {profile_id} not found",
        )

    accessible = await _get_accessible_fips(current_user, db)
    _assert_county_access(profile.county_fips, accessible, current_user.is_superuser)

    return profile


async def _get_owned_profile(
    profile_id: int,
    current_user: User,
    db: AsyncSession,
) -> FilterProfile:
    """Return a profile the user owns and may mutate.

    Raises 404 if not found.
    Raises 403 if system profile or belongs to another user.
    Superusers may mutate any non-system profile.
    """
    result = await db.execute(
        select(FilterProfile).where(
            FilterProfile.id == profile_id,
        )
    )
    profile: FilterProfile | None = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter profile {profile_id} not found",
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

    if not current_user.is_superuser:
        accessible = await _get_accessible_fips(current_user, db)
        _assert_county_access(profile.county_fips, accessible, current_user.is_superuser)

    return profile


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[FilterProfileResponse])
async def list_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FilterProfileResponse]:
    if current_user.is_superuser:
        stmt = (
            select(FilterProfile)
            .order_by(FilterProfile.user_id.nullsfirst(), FilterProfile.profile_name)
        )
        result = await db.execute(stmt)
        profiles = result.scalars().all()
        return [FilterProfileResponse.model_validate(p) for p in profiles]

    stmt = (
        select(FilterProfile)
        .where(
            (FilterProfile.user_id.is_(None))
            | (FilterProfile.user_id == current_user.id),
        )
        .order_by(FilterProfile.user_id.nullsfirst(), FilterProfile.profile_name)
    )
    result = await db.execute(stmt)
    profiles = result.scalars().all()

    accessible = await _get_accessible_fips(current_user, db)
    visible = [
        p for p in profiles
        if all(f in accessible for f in p.county_fips)
    ]
    return [FilterProfileResponse.model_validate(p) for p in visible]


@router.post("", response_model=FilterProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    current_user: User = Depends(get_current_user),
    body: FilterProfileCreateRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> FilterProfileResponse:
    accessible = await _get_accessible_fips(current_user, db)
    _assert_county_access(body.county_fips, accessible, current_user.is_superuser)

    profile = FilterProfile(
        profile_name=body.profile_name,
        county_fips=body.county_fips,
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
    current_user: User = Depends(get_current_user),
    profile_id: int = Path(..., description="ID of the profile to clone"),
    body: CloneProfileRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> FilterProfileResponse:
    source = await _get_visible_profile(profile_id, current_user, db)

    target_fips = body.county_fips if body.county_fips is not None else source.county_fips

    accessible = await _get_accessible_fips(current_user, db)
    _assert_county_access(target_fips, accessible, current_user.is_superuser)

    clone = FilterProfile(
        profile_name=body.profile_name,
        county_fips=target_fips,
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
    current_user: User = Depends(get_current_user),
    profile_id: int = Path(..., description="ID of the profile to update"),
    body: FilterProfileUpdateRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> FilterProfileResponse:
    profile = await _get_owned_profile(profile_id, current_user, db)

    update_data = body.model_dump(exclude_unset=True)

    if "county_fips" in update_data:
        accessible = await _get_accessible_fips(current_user, db)
        _assert_county_access(
            update_data["county_fips"], accessible, current_user.is_superuser
        )

    for field, value in update_data.items():
        setattr(profile, field, value)

    profile.version += 1

    await db.flush()
    await db.refresh(profile)
    return FilterProfileResponse.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    current_user: User = Depends(get_current_user),
    profile_id: int = Path(..., description="ID of the profile to delete"),
    db: AsyncSession = Depends(get_db),
) -> None:
    profile = await _get_owned_profile(profile_id, current_user, db)
    await db.delete(profile)
    await db.flush()


@router.patch(
    "/{profile_id}/favorite",
    response_model=ToggleFavoriteResponse,
)
async def toggle_favorite(
    current_user: User = Depends(get_current_user),
    profile_id: int = Path(..., description="ID of the profile to favorite/unfavorite"),
    db: AsyncSession = Depends(get_db),
) -> ToggleFavoriteResponse:
    await _get_visible_profile(profile_id, current_user, db)

    result = await db.execute(
        select(UserProfilePrefs).where(
            UserProfilePrefs.user_id == current_user.id,
            UserProfilePrefs.profile_id == profile_id,
        )
    )
    prefs: UserProfilePrefs | None = result.scalar_one_or_none()

    if prefs is None:
        prefs = UserProfilePrefs(
            user_id=current_user.id,
            profile_id=profile_id,
            is_favorite=True,
            run_count=0,
        )
        db.add(prefs)
    else:
        prefs.is_favorite = not prefs.is_favorite

    await db.flush()
    await db.refresh(prefs)
    return ToggleFavoriteResponse(is_favorite=prefs.is_favorite)
