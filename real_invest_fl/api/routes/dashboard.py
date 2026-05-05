"""
Dashboard route — cross-county summary for the current user.

GET /dashboard
    Returns per-county listing activity and workflow counts,
    scoped to counties the current user is authorised to access.
    Superusers see all active counties.

Outreach activity omitted until outreach_log schema is complete.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import get_current_user, get_db
from real_invest_fl.db.models.county import County
from real_invest_fl.db.models.listing_event import ListingEvent
from real_invest_fl.db.models.user import User
from real_invest_fl.db.models.user_county_access import UserCountyAccess

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

INACTIVE_STATUSES: frozenset[str] = frozenset({"REJECTED", "CLOSED"})


# ── Schemas ──────────────────────────────────────────────────────────────

class WorkflowCounts(BaseModel):
    NEW: int = 0
    REVIEWED: int = 0
    APPROVE_SEND: int = 0
    SENT: int = 0
    RESPONDED: int = 0
    REJECTED: int = 0
    CLOSED: int = 0


class CountySummary(BaseModel):
    county_fips: str
    county_name: str
    active_listings: int
    new_signals_last_7_days: int
    workflow_counts: WorkflowCounts


class DashboardResponse(BaseModel):
    counties: list[CountySummary]
    total_active_listings: int
    total_new_signals_last_7_days: int


# ── Route ────────────────────────────────────────────────────────────────

@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Return cross-county listing activity summary for the current user.

    Scoped to counties the user is authorised to access.
    Superusers see all active counties.
    Per-county figures:
        active_listings         — workflow_status NOT IN (REJECTED, CLOSED)
        new_signals_last_7_days — created_at >= now() - 7 days
        workflow_counts         — count per workflow_status
    Totals are cross-county rollups of the per-county figures.
    """
    # Fetch authorised counties
    if current_user.is_superuser:
        county_result = await db.execute(
            select(County)
            .where(County.active.is_(True))
            .order_by(County.county_name)
        )
    else:
        county_result = await db.execute(
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
    counties = county_result.scalars().all()

    if not counties:
        return DashboardResponse(
            counties=[],
            total_active_listings=0,
            total_new_signals_last_7_days=0,
        )

    authorised_fips = [c.county_fips for c in counties]
    county_name_map = {c.county_fips: c.county_name for c in counties}
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    # Fetch workflow_status counts per county in one query
    wf_result = await db.execute(
        select(
            ListingEvent.county_fips,
            ListingEvent.workflow_status,
            func.count().label("cnt"),
        )
        .where(ListingEvent.county_fips.in_(authorised_fips))
        .group_by(ListingEvent.county_fips, ListingEvent.workflow_status)
    )
    wf_rows = wf_result.all()

    # Fetch new signals (last 7 days) per county in one query
    new_result = await db.execute(
        select(
            ListingEvent.county_fips,
            func.count().label("cnt"),
        )
        .where(
            ListingEvent.county_fips.in_(authorised_fips),
            ListingEvent.created_at >= cutoff,
        )
        .group_by(ListingEvent.county_fips)
    )
    new_rows = new_result.all()

    # Index results by county_fips
    wf_by_county: dict[str, dict[str, int]] = {fips: {} for fips in authorised_fips}
    for row in wf_rows:
        wf_by_county[row.county_fips][row.workflow_status] = row.cnt

    new_by_county: dict[str, int] = {row.county_fips: row.cnt for row in new_rows}

    # Build per-county summaries
    summaries: list[CountySummary] = []
    total_active = 0
    total_new = 0

    for fips in authorised_fips:
        wf = wf_by_county.get(fips, {})

        active = sum(
            cnt for st, cnt in wf.items()
            if st not in INACTIVE_STATUSES
        )
        new_signals = new_by_county.get(fips, 0)

        total_active += active
        total_new += new_signals

        summaries.append(CountySummary(
            county_fips=fips,
            county_name=county_name_map[fips],
            active_listings=active,
            new_signals_last_7_days=new_signals,
            workflow_counts=WorkflowCounts(
                NEW=wf.get("NEW", 0),
                REVIEWED=wf.get("REVIEWED", 0),
                APPROVE_SEND=wf.get("APPROVE_SEND", 0),
                SENT=wf.get("SENT", 0),
                RESPONDED=wf.get("RESPONDED", 0),
                REJECTED=wf.get("REJECTED", 0),
                CLOSED=wf.get("CLOSED", 0),
            ),
        ))

    return DashboardResponse(
        counties=summaries,
        total_active_listings=total_active,
        total_new_signals_last_7_days=total_new,
    )
