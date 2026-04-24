"""Shared pytest fixtures."""
import pytest


@pytest.fixture
def sample_parcel_id() -> str:
    return "012345678901234567"
