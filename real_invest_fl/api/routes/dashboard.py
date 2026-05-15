"""
Dashboard route — profile activity and outreach pipeline status
for the current user.

GET /dashboard
    (1) Profile activity list: user_profile_prefs joined to
        filter_profiles, ordered by is_favorite DESC,
        last_searched_at DESC NULLS LAST, run_count DESC.
        Includes all profiles the user has a prefs row for.
        No inventory counts. No listing_events data.

    (2) Outreach pipeline status: drafts_pending, sent_this_week,
        responses_received. Scoped to current_user only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import get_current_user, get_db
from real_invest_fl.db.models.filter_profile import FilterProfile
from real_invest_fl.db.models.outreach_log import OutreachLog
from real_invest_fl.db.models.user import User
from real_invest_fl.db.models.user_profile_prefs import UserProfilePrefs

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Schemas ──────────────────────────────────────────────────────────────

class ProfileActivityEntry(BaseModel):
    profile_id: int
    profile_name: str
    county_fips: str
    is_system: bool
    is_favorite: bool
    last_searched_at: datetime | None
    last_result_count: int | None
    run_count: int


class OutreachPipelineStatus(BaseModel):
    drafts_pending: int
    sent_this_week: int
    responses_received: int


class DashboardResponse(BaseModel):
    profile_activity: list[ProfileActivityEntry]
    outreach_pipeline: OutreachPipelineStatus


# ── Route ────────────────────────────────────────────────────────────────

@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Return profile activity list and outreach pipeline status.

    Profile activity list:
        Rows from user_profile_prefs joined to filter_profiles,
        scoped to current_user. Ordered by is_favorite DESC,
        last_searched_at DESC NULLS LAST, run_count DESC.
        is_system = True when filter_profiles.user_id IS NULL.

    Outreach pipeline status:
        drafts_pending      — outreach_log rows WHERE status = 'DRAFT'
        sent_this_week      — outreach_log rows WHERE status = 'SENT'
                              AND sent_at >= now() - 7 days
        responses_received  — always 0 until inbound webhook implemented
                              (item 23, Phase 4 tail)
    """
    # ------------------------------------------------------------------ #
    # (1) Profile activity list                                            #
    # ------------------------------------------------------------------ #
    prefs_result = await db.execute(
        select(UserProfilePrefs, FilterProfile)
        .join(
            FilterProfile,
            FilterProfile.id == UserProfilePrefs.profile_id,
        )
        .where(UserProfilePrefs.user_id == current_user.id)
        .order_by(
            UserProfilePrefs.is_favorite.desc(),
            UserProfilePrefs.last_searched_at.desc().nulls_last(),
            UserProfilePrefs.run_count.desc(),
        )
    )
    prefs_rows = prefs_result.all()

    profile_activity: list[ProfileActivityEntry] = [
        ProfileActivityEntry(
            profile_id=prefs.profile_id,
            profile_name=profile.profile_name,
            county_fips=profile.county_fips,
            is_system=profile.user_id is None,
            is_favorite=prefs.is_favorite,
            last_searched_at=prefs.last_searched_at,
            last_result_count=prefs.last_result_count,
            run_count=prefs.run_count,
        )
        for prefs, profile in prefs_rows
    ]

    # ------------------------------------------------------------------ #
    # (2) Outreach pipeline status                                         #
    # ------------------------------------------------------------------ #
    sent_cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    drafts_result = await db.execute(
        select(func.count())
        .select_from(OutreachLog)
        .where(
            OutreachLog.user_id == current_user.id,
            OutreachLog.status == "DRAFT",
        )
    )
    drafts_pending: int = drafts_result.scalar_one()

    sent_result = await db.execute(
        select(func.count())
        .select_from(OutreachLog)
        .where(
            OutreachLog.user_id == current_user.id,
            OutreachLog.status == "SENT",
            OutreachLog.sent_at >= sent_cutoff,
        )
    )
    sent_this_week: int = sent_result.scalar_one()

    return DashboardResponse(
        profile_activity=profile_activity,
        outreach_pipeline=OutreachPipelineStatus(
            drafts_pending=drafts_pending,
            sent_this_week=sent_this_week,
            responses_received=0,  # item 23 — inbound webhook, Phase 4 tail
        ),
    )
