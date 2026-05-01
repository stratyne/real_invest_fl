"""
tests/test_listing_matcher_lookup.py
--------------------------------------
Tier 1 deterministic tests for listing_matcher.lookup_parcel_by_address()
and listing_matcher.enrich_bed_bath().

No live database required — all DB interactions are stubbed via
unittest.mock. Tests lock the three-level fallback contract, county_fips
filtering, normalization behavior, and bed/bath enrichment rules.

Run:
    python -m pytest tests/test_listing_matcher_lookup.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from real_invest_fl.ingest.listing_matcher import (
    enrich_bed_bath,
    lookup_parcel_by_address,
)


# ---------------------------------------------------------------------------
# Helpers — fixture row factory
# ---------------------------------------------------------------------------

def _make_row(parcel_id="0000000000123456", county_fips="12033"):
    """Return a mock row object matching the seven-column SELECT."""
    row = MagicMock()
    row.parcel_id    = parcel_id
    row.county_fips  = county_fips
    row.jv           = 150000
    row.arv_estimate = 165000
    row.tot_lvg_area = 1200
    row.bedrooms     = None
    row.bathrooms    = None
    return row


def _make_conn(fetchone_return=None, fetchall_return=None):
    """
    Return a mock sync connection whose execute().fetchone() and
    execute().fetchall() return the supplied values.
    """
    conn = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = fetchone_return
    result.fetchall.return_value = fetchall_return if fetchall_return is not None else []
    conn.execute.return_value = result
    return conn


# ---------------------------------------------------------------------------
# lookup_parcel_by_address — Level 1 exact match
# ---------------------------------------------------------------------------

class TestLevel1ExactMatch:

    def test_suffix_abbreviation_applied(self):
        """
        '110 Frisco Road' normalizes to '110 FRISCO RD' before SQL.
        Confirms suffix abbreviation is applied inside lookup_parcel_by_address.
        Regression: Auction.com 'FRISCO ROAD' previously unmatched.
        """
        row = _make_row()
        conn = _make_conn(fetchone_return=row)

        result = lookup_parcel_by_address(conn, "110 Frisco Road", "32534")

        assert result is not None
        assert result["parcel_id"] == row.parcel_id
        # Confirm the SQL was called with the normalized form
        call_args = conn.execute.call_args_list[0]
        sql_params = call_args[0][1]  # positional params dict
        assert sql_params["street"] == "110 FRISCO RD"

    def test_directional_contraction_applied(self):
        """
        '2983 North Highway 95 A' normalizes to '2983 N HWY 95 A'.
        Regression: Auction.com 'NORTH HIGHWAY 95' previously unmatched.
        """
        row = _make_row()
        conn = _make_conn(fetchone_return=row)

        result = lookup_parcel_by_address(conn, "2983 North Highway 95 A", "32534")

        assert result is not None
        call_args = conn.execute.call_args_list[0]
        sql_params = call_args[0][1]
        assert sql_params["street"] == "2983 N HWY 95 A"

    def test_muldoon_road_suffix(self):
        """
        '5931 Muldoon Road' normalizes to '5931 MULDOON RD'.
        Regression: third Auction.com previously unmatched address.
        """
        row = _make_row()
        conn = _make_conn(fetchone_return=row)

        result = lookup_parcel_by_address(conn, "5931 Muldoon Road", "32526")

        assert result is not None
        call_args = conn.execute.call_args_list[0]
        sql_params = call_args[0][1]
        assert sql_params["street"] == "5931 MULDOON RD"

    def test_level1_with_zip_match(self):
        """Level 1 with zip returns parcel dict on match."""
        row = _make_row()
        conn = _make_conn(fetchone_return=row)

        result = lookup_parcel_by_address(conn, "100 Main Street", "32501")

        assert result is not None
        assert result["county_fips"] == "12033"

    def test_level1_without_zip_match(self):
        """Level 1 without zip still matches on street alone."""
        row = _make_row()
        # When zip_code is None, the with-zip branch is skipped entirely.
        # Only one fetchone call is made — the without-zip branch.
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.fetchone.return_value = row
        conn.execute.return_value = result_obj

        result = lookup_parcel_by_address(conn, "100 Main Street", None)

        assert result is not None
        assert result["parcel_id"] == row.parcel_id

    def test_county_fips_in_every_level1_sql_call(self):
        """
        county_fips=:fips appears in the SQL params for Level 1 calls.
        Regression: cross-county leakage if fips filter missing.
        """
        row = _make_row()
        conn = _make_conn(fetchone_return=row)

        lookup_parcel_by_address(conn, "100 Main St", "32501", county_fips="12033")

        for c in conn.execute.call_args_list:
            params = c[0][1]
            assert "fips" in params, "county_fips filter missing from SQL params"
            assert params["fips"] == "12033"

    def test_ordinal_suffix_not_split(self):
        """
        '905 N 74TH AVE' — no space injected between 7 and 4 or 4 and TH.
        Regression: ordinal-safe lookahead in _DIGIT_LETTER_RE.
        """
        row = _make_row()
        conn = _make_conn(fetchone_return=row)

        lookup_parcel_by_address(conn, "905 N 74th Ave", "32507")

        call_args = conn.execute.call_args_list[0]
        sql_params = call_args[0][1]
        assert sql_params["street"] == "905 N 74TH AVE"
        assert "7 4" not in sql_params["street"]
        assert "4 TH" not in sql_params["street"]

    def test_partially_normalized_input_accepted(self):
        """
        Partially normalized input (from _normalize_street()) is accepted.
        normalize_street_address() applied internally — idempotent on
        already-uppercased input.
        Regression: Auction.com adapter path correctness.
        """
        row = _make_row()
        conn = _make_conn(fetchone_return=row)

        # Simulates what _normalize_street() produces for '110 Frisco Road':
        # digit-letter injection + upper — but NOT suffix abbreviation
        partially_normalized = "110 FRISCO ROAD"
        result = lookup_parcel_by_address(conn, partially_normalized, "32534")

        assert result is not None
        call_args = conn.execute.call_args_list[0]
        sql_params = call_args[0][1]
        # Centralized function must have applied suffix abbreviation
        assert sql_params["street"] == "110 FRISCO RD"

    def test_returns_none_on_no_match_any_level(self):
        """Returns None when all three levels fail."""
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.fetchone.return_value = None
        result_obj.fetchall.return_value = []
        conn.execute.return_value = result_obj

        result = lookup_parcel_by_address(conn, "999 Nowhere Lane", "99999")

        assert result is None

    def test_empty_street_returns_none(self):
        """Empty street input returns None immediately without DB call."""
        conn = MagicMock()
        result = lookup_parcel_by_address(conn, "", "32501")
        assert result is None
        conn.execute.assert_not_called()


# ---------------------------------------------------------------------------
# lookup_parcel_by_address — Level 2 unit normalization
# ---------------------------------------------------------------------------

class TestLevel2UnitNormalization:

    def _conn_miss_then_hit(self, hit_row):
        """
        Connection that returns None for the first two Level 1 calls,
        then returns hit_row for the first Level 2 call.
        """
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.fetchone.side_effect = [None, None, hit_row]
        result_obj.fetchall.return_value = []
        conn.execute.return_value = result_obj
        return conn

    def test_hash_unit_normalized(self):
        """
        '#4A' unit designator stripped at Level 2, not Level 1.
        '4831 OLIVE RD #4A' → Level 1 miss → Level 2 match on '4831 OLIVE RD 4A'.
        Regression: unit-bearing addresses never matching at Level 1 must
        fall through correctly to Level 2.
        """
        row = _make_row()
        conn = self._conn_miss_then_hit(row)

        result = lookup_parcel_by_address(conn, "4831 Olive Rd #4A", "32514")

        assert result is not None
        assert result["parcel_id"] == row.parcel_id
        # The Level 2 SQL call must use '4831 OLIVE RD 4A'
        level2_call = conn.execute.call_args_list[2]
        sql_params = level2_call[0][1]
        assert sql_params["street"] == "4831 OLIVE RD 4A"

    def test_apt_unit_normalized(self):
        """
        'APT 4A' variant handled at Level 2.
        '4831 OLIVE RD APT 4A' → Level 1 miss → Level 2 match on '4831 OLIVE RD 4A'.
        """
        row = _make_row()
        conn = self._conn_miss_then_hit(row)

        result = lookup_parcel_by_address(conn, "4831 Olive Rd APT 4A", "32514")

        assert result is not None
        level2_call = conn.execute.call_args_list[2]
        sql_params = level2_call[0][1]
        assert sql_params["street"] == "4831 OLIVE RD 4A"

    def test_unit_preserved_for_level2_not_stripped_at_level1(self):
        """
        Level 1 SQL uses the unit-stripped form (street_norm).
        Level 2 SQL uses the recombined "{base} {unit}" form.
        These must be different strings when a unit is present.
        Regression: stripping unit too early collapses Level 1 and
        Level 2 into the same query, making Level 2 unreachable.
        """
        row = _make_row()
        conn = self._conn_miss_then_hit(row)

        lookup_parcel_by_address(conn, "4831 Olive Rd #4A", "32514")

        level1_params = conn.execute.call_args_list[0][0][1]
        level2_params = conn.execute.call_args_list[2][0][1]
        # Level 1 should NOT contain the unit
        assert "4A" not in level1_params["street"]
        # Level 2 SHOULD contain the unit value
        assert "4A" in level2_params["street"]

    def test_county_fips_in_level2_sql(self):
        """county_fips filter present in Level 2 SQL params."""
        row = _make_row()
        conn = self._conn_miss_then_hit(row)

        lookup_parcel_by_address(
            conn, "4831 Olive Rd #4A", "32514", county_fips="12033"
        )

        for c in conn.execute.call_args_list:
            params = c[0][1]
            assert params.get("fips") == "12033"


# ---------------------------------------------------------------------------
# lookup_parcel_by_address — Level 3 LIKE prefix
# ---------------------------------------------------------------------------

class TestLevel3Prefix:

    def _conn_all_miss(self, fetchall_return):
        """All fetchone calls return None; fetchall returns supplied list."""
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.fetchone.return_value = None
        result_obj.fetchall.return_value = fetchall_return
        conn.execute.return_value = result_obj
        return conn

    def test_single_prefix_match_returns_parcel(self):
        """
        Level 3 single result: returns the parcel dict.
        Regression: Level 3 returning None on valid single match.
        """
        row = _make_row()
        conn = self._conn_all_miss([row])

        result = lookup_parcel_by_address(conn, "100 Main Street", "32501")

        assert result is not None
        assert result["parcel_id"] == row.parcel_id

    def test_multi_unit_emits_review_and_returns_none(self, capsys):
        """
        Level 3 multiple results: emits [REVIEW] MULTI-UNIT to stdout,
        returns None.
        Regression: silent incorrect parcel assignment on multi-unit match.
        """
        row1 = _make_row(parcel_id="1111111111111111")
        row2 = _make_row(parcel_id="2222222222222222")
        conn = self._conn_all_miss([row1, row2])

        result = lookup_parcel_by_address(conn, "100 Main Street", "32501")

        assert result is None
        captured = capsys.readouterr()
        assert "[REVIEW] MULTI-UNIT" in captured.out
        assert "1111111111111111" in captured.out
        assert "2222222222222222" in captured.out
        assert "manual selection required" in captured.out

    def test_level3_prefix_uses_unit_stripped_form(self):
        """
        Level 3 LIKE prefix is extracted from street_norm (unit-stripped),
        not from street_with_unit. Ensures no unit fragment in the LIKE anchor.
        Regression: unit string corrupting LIKE prefix.
        """
        row = _make_row()
        conn = self._conn_all_miss([row])

        # Address with a unit — the LIKE prefix must NOT contain '#' or '4A'
        lookup_parcel_by_address(conn, "4831 Olive Rd #4A", "32514")

        # The fetchall call is the Level 3 call
        fetchall_call = None
        for c in conn.execute.call_args_list:
            sql_text = str(c[0][0])
            if "LIKE" in sql_text:
                fetchall_call = c
                break

        assert fetchall_call is not None
        prefix_param = fetchall_call[0][1].get("prefix", "")
        assert "#" not in prefix_param
        assert "4A" not in prefix_param

    def test_county_fips_in_level3_sql(self):
        """county_fips filter present in Level 3 SQL params."""
        row = _make_row()
        conn = self._conn_all_miss([row])

        lookup_parcel_by_address(
            conn, "100 Main Street", "32501", county_fips="12033"
        )

        for c in conn.execute.call_args_list:
            params = c[0][1]
            assert params.get("fips") == "12033"

    def test_zero_padding_never_applied_to_returned_parcel_id(self):
        """
        The parcel_id in the returned dict is the raw DB value.
        normalize_parcel_id() is never called — it would pad to 18 chars
        and break the join since properties.parcel_id is 16 chars.
        Regression: zero-padded ID failing subsequent joins.
        """
        row = _make_row(parcel_id="0000000000123456")  # 16 chars
        conn = _make_conn(fetchone_return=row)

        result = lookup_parcel_by_address(conn, "100 Main St", "32501")

        assert result is not None
        assert len(result["parcel_id"]) == 16
        assert result["parcel_id"] == "0000000000123456"


# ---------------------------------------------------------------------------
# enrich_bed_bath
# ---------------------------------------------------------------------------

class TestEnrichBedBath:

    def test_both_none_returns_false_no_db_call(self):
        """
        Both bedrooms and bathrooms are None → returns False immediately,
        no DB call made.
        Regression: spurious UPDATE with NULL values.
        """
        conn = MagicMock()
        result = enrich_bed_bath(
            conn, "0000000000123456", "12033", None, None, "test_source"
        )
        assert result is False
        conn.execute.assert_not_called()

    def test_existing_value_not_overwritten(self):
        """
        COALESCE + WHERE guard prevents overwriting existing non-NULL value.
        Simulated by rowcount=0 (DB found no rows where beds/baths were NULL).
        Regression: lower-confidence source overwriting existing data.
        """
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.rowcount = 0
        conn.execute.return_value = result_obj

        result = enrich_bed_bath(
            conn, "0000000000123456", "12033", 2, 1.0, "test_source"
        )
        assert result is False

    def test_null_parcel_updated_returns_true(self):
        """
        rowcount=1 (DB found a row where beds/baths were NULL and updated).
        Returns True.
        """
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.rowcount = 1
        conn.execute.return_value = result_obj

        result = enrich_bed_bath(
            conn, "0000000000123456", "12033", 3, 2.0, "auction_com"
        )
        assert result is True

    def test_dry_run_returns_true_no_db_call(self):
        """
        dry_run=True with non-None inputs → returns True, no DB mutation.
        Regression: dry-run accidentally writing to DB.
        """
        conn = MagicMock()
        result = enrich_bed_bath(
            conn, "0000000000123456", "12033", 3, 2.0, "zillow_foreclosure",
            dry_run=True
        )
        assert result is True
        conn.execute.assert_not_called()

    def test_dry_run_both_none_returns_false(self):
        """dry_run=True but both values None → still returns False."""
        conn = MagicMock()
        result = enrich_bed_bath(
            conn, "0000000000123456", "12033", None, None, "test_source",
            dry_run=True
        )
        assert result is False
        conn.execute.assert_not_called()

    def test_sql_uses_coalesce_not_direct_assignment(self):
        """
        The UPDATE SQL must use COALESCE(bedrooms, :beds) not bare SET bedrooms = :beds.
        Locks the DB-layer enforcement of non-overwrite rule.
        Regression: direct assignment overwriting any existing value.
        """
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.rowcount = 1
        conn.execute.return_value = result_obj

        enrich_bed_bath(
            conn, "0000000000123456", "12033", 3, 2.0, "auction_com"
        )

        sql_text = str(conn.execute.call_args_list[0][0][0])
        assert "COALESCE(bedrooms" in sql_text
        assert "COALESCE(bathrooms" in sql_text
        assert "COALESCE(bed_bath_source" in sql_text

    def test_sql_where_clause_guards_null_check(self):
        """
        WHERE clause must include (bedrooms IS NULL OR bathrooms IS NULL).
        Locks the guard that prevents any update when both columns are populated.
        """
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.rowcount = 0
        conn.execute.return_value = result_obj

        enrich_bed_bath(
            conn, "0000000000123456", "12033", 3, 2.0, "auction_com"
        )

        sql_text = str(conn.execute.call_args_list[0][0][0])
        assert "bedrooms IS NULL OR bathrooms IS NULL" in sql_text

    def test_source_name_passed_as_parameter(self):
        """
        source_name is passed as :src bind parameter, not hardcoded.
        Locks that Zillow and Auction.com each write their own source name.
        """
        conn = MagicMock()
        result_obj = MagicMock()
        result_obj.rowcount = 1
        conn.execute.return_value = result_obj

        enrich_bed_bath(
            conn, "0000000000123456", "12033", 3, 2.0, "zillow_foreclosure"
        )

        bind_params = conn.execute.call_args_list[0][0][1]
        assert bind_params["src"] == "zillow_foreclosure"


# ---------------------------------------------------------------------------
# normalize_street_address — strip_unit=False path preserved
# ---------------------------------------------------------------------------

class TestNormalizeStreetAddressStripUnitFalse:

    def test_strip_unit_false_preserves_hash_unit(self):
        """
        strip_unit=False returns address with unit designator intact and
        unit value not corrupted by digit-letter injection.
        '#4A' must not be split to '#4 A'.
        Regression: strip_unit=False silently broken by refactor.
        """
        from real_invest_fl.utils.text import normalize_street_address

        result = normalize_street_address("4831 Olive Rd #4A", strip_unit=False)
        assert result == "4831 OLIVE RD #4A"

    def test_strip_unit_true_removes_hash_unit(self):
        """
        strip_unit=True (default) removes unit designator.
        Baseline behavior must be unchanged.
        """
        from real_invest_fl.utils.text import normalize_street_address

        result = normalize_street_address("4831 Olive Rd #4A", strip_unit=True)
        assert "#" not in result
        assert result == "4831 OLIVE RD"
