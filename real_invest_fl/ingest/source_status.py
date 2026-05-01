"""
source_status.py — shared write-path helper for data_source_status.

Call update_source_status() at the end of every ingest runner (success
or failure) to keep the UI status board current.

Caller responsibilities:
- Supply the exact source string used in listing_events.source
- Supply a human-readable display_name for the UI
- Supply county_fips for the row's composite key
- Supply status: 'SUCCESS' | 'FAILED' | 'PARTIAL'
- Supply record_count and error_message as appropriate

This module does NOT define shared SOURCE_* constants. Each runner
owns its own source key. This avoids inventing values for sources
whose files have not been verified.

Write pattern:
- Uses sync engine (settings.sync_database_url) per project convention
- Uses text() SQL per project convention
- Upsert: INSERT ... ON CONFLICT (source, county_fips) DO UPDATE
- last_success_at is updated only when status = 'SUCCESS'
- last_run_at is always set to now() (completion timestamp)
- last_error_message is cleared to NULL on SUCCESS
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_VALID_STATUSES = frozenset({"SUCCESS", "FAILED", "PARTIAL"})

_UPSERT_SQL = text("""
    INSERT INTO data_source_status (
        source,
        county_fips,
        display_name,
        last_success_at,
        last_run_at,
        last_run_status,
        last_record_count,
        last_error_message,
        created_at,
        updated_at
    )
    VALUES (
        :source,
        :county_fips,
        :display_name,
        CASE WHEN :status = 'SUCCESS' THEN now() ELSE NULL END,
        now(),
        :status,
        :record_count,
        :error_message,
        now(),
        now()
    )
    ON CONFLICT (source, county_fips) DO UPDATE SET
        display_name        = EXCLUDED.display_name,
        last_run_at         = now(),
        last_run_status     = EXCLUDED.last_run_status,
        last_record_count   = EXCLUDED.last_record_count,
        last_error_message  = EXCLUDED.last_error_message,
        last_success_at     = CASE
                                  WHEN EXCLUDED.last_run_status = 'SUCCESS'
                                  THEN now()
                                  ELSE data_source_status.last_success_at
                              END,
        updated_at          = now()
""")


def update_source_status(
    engine: Engine,
    *,
    source: str,
    display_name: str,
    county_fips: str,
    status: str,
    record_count: int | None = None,
    error_message: str | None = None,
) -> None:
    """Upsert one row in data_source_status.

    Parameters
    ----------
    engine:
        Sync SQLAlchemy engine (settings.sync_database_url).
    source:
        Source key — must exactly match listing_events.source for this
        runner. Supplied by the caller from its own verified constant.
    display_name:
        Human-readable label for the UI status dashboard.
        Supplied by the caller.
    county_fips:
        FIPS code for the county this source serves.
        Forms the second half of the composite primary key.
    status:
        Run outcome. Must be 'SUCCESS', 'FAILED', or 'PARTIAL'.
    record_count:
        Records inserted or updated in this run. Pass None if unknown.
    error_message:
        Short error string when status is 'FAILED'. Pass None on
        SUCCESS — this clears any previously stored error message.

    Raises
    ------
    ValueError
        If status is not one of the three valid values.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"update_source_status: invalid status {status!r}. "
            f"Must be one of: {sorted(_VALID_STATUSES)}"
        )

    with engine.begin() as conn:
        conn.execute(
            _UPSERT_SQL,
            {
                "source":        source,
                "county_fips":   county_fips,
                "display_name":  display_name,
                "status":        status,
                "record_count":  record_count,
                "error_message": error_message,
            },
        )

    logger.info(
        "data_source_status updated | source=%s | county_fips=%s | "
        "status=%s | records=%s",
        source,
        county_fips,
        status,
        record_count,
    )
