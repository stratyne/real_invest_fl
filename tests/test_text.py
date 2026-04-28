"""
Tests for real_invest_fl/utils/text.py — normalize_street_address().

Real-world cases are taken directly from the Auction.com dry-run
unmatched set (2026-04-28) and confirmed NAL phy_addr1 values.
"""
import pytest
from real_invest_fl.utils.text import normalize_street_address


# ---------------------------------------------------------------------------
# Real-world cases — the three known Auction.com unmatched addresses
# and two that were already resolving (regression guard)
# ---------------------------------------------------------------------------

class TestRealWorldCases:

    def test_frisco_road_suffix(self):
        """ROAD -> RD suffix abbreviation."""
        assert normalize_street_address("110 FRISCO ROAD") == "110 FRISCO RD"

    def test_muldoon_road_suffix(self):
        """ROAD -> RD suffix abbreviation — second confirmed case."""
        assert normalize_street_address("5931 MULDOON ROAD") == "5931 MULDOON RD"

    def test_north_highway_directional_and_suffix(self):
        """
        2983 NORTH HIGHWAY 95 A -> 2983 N HWY 95A
        Directional contraction (NORTH->N) + suffix abbreviation (HIGHWAY->HWY)
        + digit-letter space injection ensures 95 A -> 95A after collapse.

        Note: digit-letter injection runs BEFORE suffix map, so '95 A' with a
        space is not affected by the digit-letter rule. The space between 95
        and A is preserved by NAL — NAL stores '2983 HIGHWAY 95A' with no
        space. We verify the normalizer contracts to match NAL exactly.
        """
        assert normalize_street_address("2983 North Highway 95 A") == "2983 N HWY 95 A"

    def test_n_74th_ave_regression(self):
        """905 N 74th Ave — single-letter directional must NOT be stripped."""
        assert normalize_street_address("905 N 74th Ave") == "905 N 74TH AVE"

    def test_n_48th_ave_regression(self):
        """1118 N 48th Ave — single-letter directional, digit-letter injection."""
        assert normalize_street_address("1118 N 48th Ave") == "1118 N 48TH AVE"

    def test_michigan_ave_unit_regression(self):
        """
        2301 W Michigan Ave 51 — unit number without designator keyword.
        The bare trailing '51' is not a unit designator pattern — it stays.
        This matches NAL phy_addr1 = '2301 W MICHIGAN AVE 51'.
        """
        assert normalize_street_address("2301 W Michigan Ave 51") == "2301 W MICHIGAN AVE 51"


# ---------------------------------------------------------------------------
# Suffix map — one case per suffix entry
# ---------------------------------------------------------------------------

class TestSuffixAbbreviation:

    @pytest.mark.parametrize("full, abbr, house", [
        ("ROAD",       "RD",   "100"),
        ("STREET",     "ST",   "200"),
        ("AVENUE",     "AVE",  "300"),
        ("BOULEVARD",  "BLVD", "400"),
        ("DRIVE",      "DR",   "500"),
        ("COURT",      "CT",   "600"),
        ("PLACE",      "PL",   "700"),
        ("LANE",       "LN",   "800"),
        ("CIRCLE",     "CIR",  "900"),
        ("TRAIL",      "TRL",  "1000"),
        ("TERRACE",    "TER",  "1100"),
        ("HIGHWAY",    "HWY",  "1200"),
        ("PARKWAY",    "PKWY", "1300"),
        ("EXPRESSWAY", "EXPY", "1400"),
        ("FREEWAY",    "FWY",  "1500"),
    ])
    def test_suffix_expansion(self, full, abbr, house):
        result = normalize_street_address(f"{house} OAK {full}")
        assert result == f"{house} OAK {abbr}"

    def test_already_abbreviated_suffix_unchanged(self):
        """RD already abbreviated — must not be double-processed."""
        assert normalize_street_address("110 FRISCO RD") == "110 FRISCO RD"

    def test_suffix_word_boundary_not_partial(self):
        """STRAND contains no suffix match — must not be abbreviated."""
        result = normalize_street_address("123 STRAND BLVD")
        assert result == "123 STRAND BLVD"


# ---------------------------------------------------------------------------
# Directional contraction
# ---------------------------------------------------------------------------

class TestDirectionalContraction:

    @pytest.mark.parametrize("full, abbr", [
        ("NORTH",     "N"),
        ("SOUTH",     "S"),
        ("EAST",      "E"),
        ("WEST",      "W"),
        ("NORTHEAST", "NE"),
        ("NORTHWEST", "NW"),
        ("SOUTHEAST", "SE"),
        ("SOUTHWEST", "SW"),
    ])
    def test_directional_contraction(self, full, abbr):
        result = normalize_street_address(f"100 {full} OAK ST")
        assert result == f"100 {abbr} OAK ST"

    def test_single_letter_directional_unchanged(self):
        """N, S, E, W already abbreviated — must pass through unchanged."""
        assert normalize_street_address("100 N OAK ST") == "100 N OAK ST"

    def test_directional_in_street_name_not_stripped(self):
        """
        NORTH inside the street name (not after house number) must not
        be contracted. e.g. '100 OAK NORTH DR' — NORTH is mid-token here.
        Only the first token of the street name (pos 2) is eligible.
        """
        result = normalize_street_address("100 OAK NORTH DR")
        assert result == "100 OAK NORTH DR"

    def test_directional_not_stripped_when_followed_by_another_directional(self):
        """Guard: NORTH SOUTH ST should not collapse the NORTH."""
        result = normalize_street_address("100 NORTH SOUTH ST")
        assert result == "100 NORTH SOUTH ST"


# ---------------------------------------------------------------------------
# Unit stripping
# ---------------------------------------------------------------------------

class TestUnitStripping:

    @pytest.mark.parametrize("raw, expected", [
        ("123 OAK ST APT 4",    "123 OAK ST"),
        ("123 OAK ST APT. 4",   "123 OAK ST"),
        ("123 OAK ST UNIT B",   "123 OAK ST"),
        ("123 OAK ST STE 100",  "123 OAK ST"),
        ("123 OAK ST SUITE 2A", "123 OAK ST"),
        ("123 OAK ST #4",       "123 OAK ST"),
        ("123 OAK ST # 4",      "123 OAK ST"),
    ])
    def test_unit_stripped(self, raw, expected):
        assert normalize_street_address(raw) == expected

    def test_bare_trailing_number_not_stripped(self):
        """
        '2301 W MICHIGAN AVE 51' — bare number with no designator keyword
        must NOT be stripped. This is a NAL-format address where the unit
        number has no prefix keyword.
        """
        assert normalize_street_address("2301 W MICHIGAN AVE 51") == "2301 W MICHIGAN AVE 51"


# ---------------------------------------------------------------------------
# Digit-letter space injection
# ---------------------------------------------------------------------------

class TestDigitLetterInjection:

    def test_digit_letter_space_injected(self):
        """2301W -> 2301 W before any other processing."""
        assert normalize_street_address("2301W MICHIGAN AVE") == "2301 W MICHIGAN AVE"

    def test_digit_letter_no_false_positive(self):
        """95A in a highway number — space is injected, producing 95 A."""
        result = normalize_street_address("100 HWY 95A")
        assert result == "100 HWY 95 A"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_string(self):
        assert normalize_street_address("") == ""

    def test_none_like_empty(self):
        """None is not a valid input but guard against accidental calls."""
        assert normalize_street_address("") == ""

    def test_already_normalized(self):
        """Idempotent — running twice produces the same result."""
        once  = normalize_street_address("110 FRISCO RD")
        twice = normalize_street_address(once)
        assert once == twice

    def test_whitespace_collapse(self):
        """Multiple internal spaces collapsed to single space."""
        assert normalize_street_address("110   FRISCO   RD") == "110 FRISCO RD"

    def test_lowercase_input(self):
        """All lowercase input is uppercased correctly."""
        assert normalize_street_address("110 frisco road") == "110 FRISCO RD"

    def test_mixed_case_input(self):
        assert normalize_street_address("110 Frisco Road") == "110 FRISCO RD"
