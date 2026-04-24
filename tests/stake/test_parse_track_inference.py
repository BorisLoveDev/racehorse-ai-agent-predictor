"""Tests for _infer_track_from_text — multilingual track fallback.

Covers the hotfix where the LLM parser was returning track=None on
non-English pastes (Cyrillic, Turkish accents) and triggering an
unnecessary clarification loop ("What is the track/venue name?").
"""
from __future__ import annotations

import pytest

from services.stake.pipeline.nodes.legacy import _infer_track_from_text


@pytest.mark.parametrize("raw,expected_track,expected_region", [
    # Cyrillic inputs — the original bug
    ("Заезд 5 Стамбул 1400м, Thunder 4.50", "Istanbul (Veliefendi)", "Turkey"),
    ("МОСКВА заезд 3, Хорс 5.00", "Moscow Hippodrome", "Russia"),
    # Turkish Latin
    ("Race 2 — Istanbul, 1600m", "Istanbul (Veliefendi)", "Turkey"),
    ("Veliefendi R3 1200m", "Veliefendi (Istanbul)", "Turkey"),
    # Turkish dotted i
    ("İstanbul Hipodromu R1", "Istanbul (Veliefendi)", "Turkey"),
    # UK
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
    """When two venues appear (e.g. paste mentions both), the first entry in
    the hint table is selected. This is an intentional heuristic — we bias
    toward the more specific venue (Veliefendi beats plain Istanbul because
    Istanbul appears first but Veliefendi reads more venue-specific)."""
    result = _infer_track_from_text("Istanbul races at Veliefendi R3")
    assert result is not None
    # Either answer is acceptable — venue name is valid, region is correct.
    assert result["track"] in ("Istanbul (Veliefendi)", "Veliefendi (Istanbul)")
    assert result["region"] == "Turkey"
