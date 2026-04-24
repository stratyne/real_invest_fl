"""Tests for utility functions."""
from real_invest_fl.utils.text import clean_text, parse_money, normalize_keyword_text
from real_invest_fl.utils.parcel_id import normalize_parcel_id


def test_clean_text_collapses_whitespace():
    assert clean_text("  hello   world  ") == "hello world"


def test_parse_money_strips_symbols():
    assert parse_money("$225,000") == 225000.0


def test_parse_money_returns_none_on_garbage():
    assert parse_money("n/a") is None


def test_normalize_keyword_text():
    result = normalize_keyword_text("Concrete", "BLOCK", "Home")
    assert result == "concrete block home"


def test_normalize_parcel_id_escambia_pads_to_18():
    result = normalize_parcel_id("123456", "12033")
    assert len(result) == 18
    assert result == "000000000000123456"
