"""
IngestRunContext — async context manager for pipeline run lifecycle.

Opens an IngestRun record on entry, updates counters during processing,
closes the record with final status and duration on exit.

Usage:
    async with IngestRunContext(
        session=session,
        run_type="NAL",
        county_fips="12033",
        source_file="NAL27F202502VAB.csv",
        filter_profile_id=1,
    ) as run:
        for record in records:
            result = process(record)
            run.increment(result)
"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from real_invest_fl.db.models.ingest_run import IngestRun
import logging

logger = logging.getLogger(__name__)

# Valid increment outcomes — every processed record must resolve to one
IncrementOutcome = Literal["inserted", "updated", "rejected", "skipped"]

# Valid run types — enforced at construction time
RUN_TYPES = {"NAL", "CAMA", "GIS", "LISTING", "ZESTIMATE"}


class IngestRunContext:
    """
    Async context manager that wraps a single pipeline run.

    On __aenter__:
        - Validates run_type
        - Creates an IngestRun row with status='RUNNING'
        - Flushes to DB so the row is visible immediately
        - Returns self so the caller can call run.increment()

    On __aexit__ (success):
        - Sets run_status='SUCCESS'
        - Writes all counters and rejection_summary
        - Computes duration_seconds
        - Commits

    On __aexit__ (exception):
        - Sets run_status='FAILED'
        - Captures error_message and error_traceback
        - Writes all counters accumulated before failure
        - Computes duration_seconds
        - Commits — the run record is always saved even on failure
        - Re-raises the exception so the caller sees it
    """

    def __init__(
        self,
        session: AsyncSession,
        run_type: str,
        county_fips: str,
        source_file: str | None = None,
        filter_profile_id: int | None = None,
    ) -> None:
        if run_type not in RUN_TYPES:
            raise ValueError(
                f"Invalid run_type '{run_type}'. "
                f"Must be one of: {sorted(RUN_TYPES)}"
            )

        self._session = session
        self._run_type = run_type
        self._county_fips = county_fips
        self._source_file = source_file
        self._filter_profile_id = filter_profile_id

        # Counters — incremented during processing
        self._records_read: int = 0
        self._records_inserted: int = 0
        self._records_updated: int = 0
        self._records_rejected: int = 0
        self._records_skipped: int = 0

        # Rejection reason accumulator — {"reason_code": count}
        self._rejection_summary: dict[str, int] = {}

        # Set on __aenter__
        self._run: IngestRun | None = None
        self._started_at: datetime | None = None

    # ------------------------------------------------------------------ #
    # Public API — called by pipeline code during processing              #
    # ------------------------------------------------------------------ #

    def increment(
        self,
        outcome: IncrementOutcome,
        rejection_reason: str | None = None,
    ) -> None:
        """
        Record the outcome of one processed record.

        Args:
            outcome:          One of 'inserted', 'updated', 'rejected', 'skipped'
            rejection_reason: Required when outcome='rejected'.
                              Used to build rejection_summary.
                              e.g. 'dor_uc_mismatch', 'year_built_too_old',
                                   'imp_qual_out_of_range', 'living_area_too_small'
        """
        self._records_read += 1

        if outcome == "inserted":
            self._records_inserted += 1
        elif outcome == "updated":
            self._records_updated += 1
        elif outcome == "rejected":
            self._records_rejected += 1
            if rejection_reason:
                self._rejection_summary[rejection_reason] = (
                    self._rejection_summary.get(rejection_reason, 0) + 1
                )
            else:
                # Rejection without a reason code is a pipeline bug —
                # log it but do not raise so processing continues
                logger.warning(
                    "increment() called with outcome='rejected' "
                    "but no rejection_reason provided. "
                    "run_type=%s county_fips=%s",
                    self._run_type,
                    self._county_fips,
                )
                self._rejection_summary["__unspecified__"] = (
                    self._rejection_summary.get("__unspecified__", 0) + 1
                )
        elif outcome == "skipped":
            self._records_skipped += 1
        else:
            raise ValueError(
                f"Invalid outcome '{outcome}'. "
                f"Must be one of: inserted, updated, rejected, skipped"
            )

    @property
    def records_read(self) -> int:
        return self._records_read

    @property
    def records_inserted(self) -> int:
        return self._records_inserted

    @property
    def records_updated(self) -> int:
        return self._records_updated

    @property
    def records_rejected(self) -> int:
        return self._records_rejected

    @property
    def records_skipped(self) -> int:
        return self._records_skipped

    # ------------------------------------------------------------------ #
    # Context manager protocol                                             #
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "IngestRunContext":
        self._started_at = datetime.now(tz=timezone.utc)

        self._run = IngestRun(
            run_type=self._run_type,
            county_fips=self._county_fips,
            source_file=self._source_file,
            run_status="RUNNING",
            started_at=self._started_at,
            filter_profile_id=self._filter_profile_id,
        )

        self._session.add(self._run)
        await self._session.flush()
        # flush — not commit — so the row is visible within the transaction
        # but the session stays open for pipeline inserts/updates

        logger.info(
            "Ingest run started | id=%s run_type=%s county_fips=%s source=%s",
            self._run.id,
            self._run_type,
            self._county_fips,
            self._source_file or "n/a",
        )

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        completed_at = datetime.now(tz=timezone.utc)
        duration = int((completed_at - self._started_at).total_seconds())

        # Write all counters regardless of success or failure
        self._run.completed_at = completed_at
        self._run.duration_seconds = duration
        self._run.records_read = self._records_read
        self._run.records_inserted = self._records_inserted
        self._run.records_updated = self._records_updated
        self._run.records_rejected = self._records_rejected
        self._run.records_skipped = self._records_skipped
        self._run.rejection_summary = (
            self._rejection_summary if self._rejection_summary else None
        )

        if exc_type is None:
            # Clean exit
            self._run.run_status = "SUCCESS"
            logger.info(
                "Ingest run SUCCESS | id=%s run_type=%s "
                "read=%d inserted=%d updated=%d "
                "rejected=%d skipped=%d duration=%ds",
                self._run.id,
                self._run_type,
                self._records_read,
                self._records_inserted,
                self._records_updated,
                self._records_rejected,
                self._records_skipped,
                duration,
            )
        else:
            # Failed — capture error details
            self._run.run_status = "FAILED"
            self._run.error_message = str(exc_val)
            self._run.error_traceback = "".join(
                traceback.format_exception(exc_type, exc_val, exc_tb)
            )
            logger.error(
                "Ingest run FAILED | id=%s run_type=%s "
                "read=%d inserted=%d updated=%d "
                "rejected=%d skipped=%d duration=%ds | %s",
                self._run.id,
                self._run_type,
                self._records_read,
                self._records_inserted,
                self._records_updated,
                self._records_rejected,
                self._records_skipped,
                duration,
                str(exc_val),
            )

        # Always commit the run record — even on failure
        # The pipeline caller sees the exception after this commit
        await self._session.commit()

        # Return False — do not suppress the exception
        return False
