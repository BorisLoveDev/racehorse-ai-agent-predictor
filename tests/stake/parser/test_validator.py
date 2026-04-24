import pytest

from services.stake.parser.models import ParsedRace, RunnerInfo
from services.stake.parser.validator import (
    MUST_HAVE_FIELDS, validate_excerpts,
)


EXPECTED_MUST_HAVE = {"track", "region", "race_number", "date", "distance", "snapshot_ts"}


def _make_race(raw_excerpts: dict | None = None) -> ParsedRace:
    race = ParsedRace(
        track="Sandown",
        region="Australia",
        race_number="R3",
        date="2026-04-24",
        distance="1200m",
        runners=[RunnerInfo(number=1, name="A", win_odds=2.5)],
    )
    race.raw_excerpts = dict(raw_excerpts or {})
    return race


def test_must_have_fields_match_spec():
    assert set(MUST_HAVE_FIELDS) == EXPECTED_MUST_HAVE


def test_all_excerpts_present_passes():
    race = _make_race({f: "source text" for f in MUST_HAVE_FIELDS})
    result = validate_excerpts(race)
    assert result.missing == []
    assert result.ok


def test_missing_excerpt_flags_field():
    race = _make_race({})
    result = validate_excerpts(race)
    assert set(result.missing) == EXPECTED_MUST_HAVE
    assert not result.ok
    assert set(race.missing_fields) == EXPECTED_MUST_HAVE


def test_empty_excerpt_counts_as_missing():
    race = _make_race({"track": "", "date": "   ", "region": "x"})
    result = validate_excerpts(race)
    assert "track" in result.missing
    assert "date" in result.missing
    assert "region" not in result.missing


def test_non_string_excerpt_counts_as_missing():
    race = _make_race({"track": None, "date": 123})
    result = validate_excerpts(race)
    assert "track" in result.missing
    assert "date" in result.missing


def test_validator_does_not_clobber_existing_missing_fields():
    race = _make_race({f: "txt" for f in MUST_HAVE_FIELDS})
    race.missing_fields = ["preexisting_flag"]
    result = validate_excerpts(race)
    assert result.ok
    # Existing flag preserved
    assert "preexisting_flag" in race.missing_fields


def test_parsed_race_new_fields_defaults():
    race = ParsedRace()
    assert race.raw_excerpts == {}
    assert race.field_confidences == {}
    assert race.missing_fields == []
    assert race.parser_model is None
    assert race.snapshot_ts is None
    assert race.source_type is None
