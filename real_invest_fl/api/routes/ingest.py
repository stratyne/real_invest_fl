"""
Ingest status route — data source health summary. Superuser only.

GET /ingest/status
    Returns data_source_status rows for all counties.
    Superuser only — raises 403 for non-superusers.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.api.deps import get_db
from real_invest_fl.db.models.data_source_status import DataSourceStatus
from real_invest_fl.db.models.user import User
from real_invest_fl.api.routes.config import require_superuser

router = APIRouter(prefix="/ingest", tags=["ingest"])


# ── Schema ───────────────────────────────────────────────────────────────

class DataSourceStatusResponse(BaseModel):
    source: str
    county_fips: str
    display_name: str
    last_success_at: datetime | None
    last_run_at: datetime | None
    last_run_status: str | None
    last_record_count: int | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Route ────────────────────────────────────────────────────────────────

@router.get("/status", response_model=list[DataSourceStatusResponse])
async def get_ingest_status(
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[DataSourceStatusResponse]:
    """Return data_source_status rows for all counties.

    Superuser only. Results ordered by county_fips, then source.
    """
    result = await db.execute(
        select(DataSourceStatus)
        .order_by(DataSourceStatus.county_fips, DataSourceStatus.source)
    )
    rows = result.scalars().all()
    return [DataSourceStatusResponse.model_validate(r) for r in rows]
