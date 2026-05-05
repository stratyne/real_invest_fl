"""
Listings routes — listing_event read access and workflow status management.

GET   /{county_fips}/listings                        — list listing_events with optional filters.
GET   /{county_fips}/listings/{listing_id}           — single listing_event detail.
PATCH /{county_fips}/listings/{listing_id}/status    — update workflow_status.
      Valid transitions enforced server-side — see DECISIONS.md.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import county_access, get_db
from real_invest_fl.db.models.listing_event import ListingEvent

router = APIRouter(prefix="/{county_fips}/listings", tags=["listings"])


# ── Workflow transition map ──────────────────────────────────────────────

VALID_STATUSES: frozenset[str] = frozenset({
    "NEW", "REVIEWED", "APPROVE_SEND", "SENT", "RESPONDED", "REJECTED", "CLOSED",
})

TRANSITIONS: dict[str, frozenset[str]] = {
    "NEW":          frozenset({"REVIEWED", "REJECTED"}),
    "REVIEWED":     frozenset({"APPROVE_SEND", "REJECTED"}),
    "APPROVE_SEND": frozenset({"SENT", "REVIEWED"}),
    "SENT":         frozenset({"RESPONDED", "CLOSED", "REJECTED"}),
    "RESPONDED":    frozenset({"CLOSED", "REVIEWED"}),
    "REJECTED":     frozenset({"REVIEWED", "CLOSED"}),
    "CLOSED":       frozenset(),
}


# ── Schemas ──────────────────────────────────────────────────────────────

class ListingEventResponse(BaseModel):
    id: int
    county_fips: str
    parcel_id: str
    signal_tier: int | None
    signal_type: str | None
    listing_type: str | None
    list_price: int | None
    list_date: date | None
    expiry_date: date | None
    days_on_market: int | None
    source: str | None
    listing_url: str | None
    listing_agent_name: str | None
    listing_agent_email: str | None
    listing_agent_phone: str | None
    mls_number: str | None
    price_per_sqft: float | None
    arv_estimate: int | None
    arv_source: str | None
    rehab_cost_estimate: int | None
    arv_spread: int | None
    zestimate_value: int | None
    zestimate_discount_pct: float | None
    zestimate_fetched_at: datetime | None
    workflow_status: str
    notes: str | None
    scraped_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StatusUpdateRequest(BaseModel):
    workflow_status: str
    notes: str | None = None


# ── Routes ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[ListingEventResponse])
async def list_listings(
    county_fips: str = Depends(county_access()),
    workflow_status: str | None = Query(None, description="Filter by workflow_status"),
    signal_tier: int | None = Query(None, description="Filter by signal_tier"),
    signal_type: str | None = Query(None, description="Filter by signal_type"),
    listing_type: str | None = Query(None, description="Filter by listing_type"),
    db: AsyncSession = Depends(get_db),
) -> list[ListingEventResponse]:
    """Return listing_events for the county with optional filters.

    All query filters are optional and combinable.
    Results ordered by created_at descending — most recent first.
    """
    stmt = (
        select(ListingEvent)
        .where(ListingEvent.county_fips == county_fips)
    )

    if workflow_status is not None:
        if workflow_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid workflow_status '{workflow_status}'. "
                       f"Valid values: {sorted(VALID_STATUSES)}",
            )
        stmt = stmt.where(ListingEvent.workflow_status == workflow_status)

    if signal_tier is not None:
        stmt = stmt.where(ListingEvent.signal_tier == signal_tier)

    if signal_type is not None:
        stmt = stmt.where(ListingEvent.signal_type == signal_type)

    if listing_type is not None:
        stmt = stmt.where(ListingEvent.listing_type == listing_type)

    stmt = stmt.order_by(ListingEvent.created_at.desc())

    result = await db.execute(stmt)
    events = result.scalars().all()
    return [ListingEventResponse.model_validate(e) for e in events]


@router.get("/{listing_id}", response_model=ListingEventResponse)
async def get_listing(
    county_fips: str = Depends(county_access()),
    listing_id: int = Path(..., description="listing_events.id"),
    db: AsyncSession = Depends(get_db),
) -> ListingEventResponse:
    """Return a single listing_event by id.

    Returns 404 if the listing does not exist within the county.
    County scope is enforced — a valid listing_id from a different
    county returns 404, not 403.
    """
    result = await db.execute(
        select(ListingEvent).where(
            ListingEvent.id == listing_id,
            ListingEvent.county_fips == county_fips,
        )
    )
    event: ListingEvent | None = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Listing {listing_id} not found in county {county_fips}",
        )

    return ListingEventResponse.model_validate(event)


@router.patch("/{listing_id}/status", response_model=ListingEventResponse)
async def update_listing_status(
    county_fips: str = Depends(county_access()),
    listing_id: int = Path(..., description="listing_events.id"),
    body: StatusUpdateRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> ListingEventResponse:
    """Update workflow_status on a listing_event.

    Valid transitions are enforced server-side per DECISIONS.md.
    Returns 422 for an invalid target status or a disallowed transition.
    Returns 404 if the listing does not exist within the county.
    If notes is provided it is appended to the existing notes field,
    separated by a newline, rather than overwriting.
    """
    if body.workflow_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid workflow_status '{body.workflow_status}'. "
                   f"Valid values: {sorted(VALID_STATUSES)}",
        )

    result = await db.execute(
        select(ListingEvent).where(
            ListingEvent.id == listing_id,
            ListingEvent.county_fips == county_fips,
        )
    )
    event: ListingEvent | None = result.scalar_one_or_none()

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Listing {listing_id} not found in county {county_fips}",
        )

    permitted = TRANSITIONS[event.workflow_status]

    if body.workflow_status not in permitted:
        if not permitted:
            detail = (
                f"Listing {listing_id} is CLOSED — no further transitions permitted."
            )
        else:
            detail = (
                f"Transition from '{event.workflow_status}' to "
                f"'{body.workflow_status}' is not permitted. "
                f"Permitted transitions: {sorted(permitted)}"
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )

    event.workflow_status = body.workflow_status

    if body.notes:
        if event.notes:
            event.notes = f"{event.notes}\n{body.notes}"
        else:
            event.notes = body.notes

    await db.flush()
    await db.refresh(event)
    return ListingEventResponse.model_validate(event)
