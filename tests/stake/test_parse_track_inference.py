"""Tests for _infer_track_from_text — multilingual track fallback.

Covers the hotfix where the LLM parser was returning track=None on
non-English pastes (Cyrillic, Turkish accents) and triggering an
unnecessary clarification loop ("What is the track/venue name?").
"""
from __future__ import annotations

import pytest

from services.stake.pipeline.nodes.legacy import _infer_track_from_text


@pytest.mark.parametrize("raw,expected_track,expected_region", [
    # Cyrillic city — return the transliterated CITY, not the venue
    ("Заезд 5 Стамбул 1400м, Thunder 4.50", "Istanbul", "Turkey"),
    ("МОСКВА заезд 3, Хорс 5.00", "Moscow", "Russia"),
    # Turkish Latin city
    ("Race 2 — Istanbul, 1600m", "Istanbul", "Turkey"),
    # Named venue literally in paste → keep venue name
    ("Veliefendi R3 1200m", "Veliefendi", "Turkey"),
    # Turkish dotted i
    ("İstanbul Hipodromu R1", "Istanbul", "Turkey"),
    # UK / Ireland
    ("Ascot R5 1m4f", "Ascot", "UK"),
    ("Cheltenham gold cup", "Cheltenham", "UK"),
    # France
    ("Chantilly R2, 2000m Turf", "Chantilly", "France"),
    # Japan
    ("Tokyo Race 11, Japan Cup", "Tokyo", "Japan"),
    # Case variations
    ("the races at RANDWICK tomorrow", "Randwick", "Australia"),
    ("flemington cup r3", "Flemington", "Australia"),
])
def test_infer_track_recognises_known_venues(raw, expected_track, expected_region):
    result = _infer_track_from_text(raw)
    assert result is not None
    assert result["track"] == expected_track
    assert result["region"] == expected_region


def test_infer_track_returns_none_for_unknown_text():
    assert _infer_track_from_text("just some chat message without venue") is None


def test_infer_track_handles_empty_input():
    assert _infer_track_from_text("") is None
    assert _infer_track_from_text(None) is None  # defensive


def test_infer_track_first_match_wins():
    """Both 'Istanbul' and 'Veliefendi' in the paste → the first matching
    entry in the hint table wins. Either value is a valid literal
    extraction — we're just asserting the output is stable and a literal
    substring of the paste (no inference)."""
    result = _infer_track_from_text("Istanbul races at Veliefendi R3")
    assert result is not None
    assert result["track"] in {"Istanbul", "Veliefendi"}
    assert result["region"] == "Turkey"


def test_infer_track_country_only_returns_none():
    """Strict rule: country name alone (no city or venue) is NOT enough.
    The clarification flow must ask — we never guess a city from a country."""
    # 'Turkey' is not in the hint table; country-only pastes should fall through.
    assert _infer_track_from_text("Race at some Turkey track 1500m") is None


def test_infer_track_does_not_invent_venue_from_city():
    """City-only paste must return the city, not a venue inferred from it.
    Regression guard against re-introducing the 'Istanbul (Veliefendi)' mapping."""
    result = _infer_track_from_text("Стамбул 3 заезд")
    assert result is not None
    assert "Veliefendi" not in result["track"]
    assert result["track"] == "Istanbul"
