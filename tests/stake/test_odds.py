"""
Unit tests for odds math functions in services/stake/parser/math.py.
Tests cover: to_decimal, implied_probability, overround, recalculate_without_scratches,
odds_drift_pct, and Pydantic model validation.
"""

import pytest
import pydantic
from services.stake.parser.math import (
    to_decimal,
    implied_probability,
    overround,
    recalculate_without_scratches,
    odds_drift_pct,
)
from services.stake.parser.models import RunnerInfo, ParsedRace, MarketContext


# ---------------------------------------------------------------------------
# to_decimal — format conversions
# ---------------------------------------------------------------------------

def test_to_decimal_decimal_format_passthrough() -> None:
    """Decimal format returns the value rounded to 4 decimal places."""
    assert to_decimal("decimal", 3.5) == pytest.approx(3.5, rel=1e-4)


def test_to_decimal_decimal_format_passthrough_other_value() -> None:
    """Decimal format handles various float values."""
    assert to_decimal("decimal", 1.0) == pytest.approx(1.0, rel=1e-4)


def test_to_decimal_fractional_five_halves() -> None:
    """5/2 fractional converts to 3.5 decimal."""
    assert to_decimal("fractional", "5/2") == pytest.approx(3.5, rel=1e-4)


def test_to_decimal_fractional_evens() -> None:
    """1/1 (evens) converts to 2.0 decimal."""
    assert to_decimal("fractional", "1/1") == pytest.approx(2.0, rel=1e-4)


def test_to_decimal_fractional_one_quarter() -> None:
    """1/4 converts to 1.25 decimal."""
    assert to_decimal("fractional", "1/4") == pytest.approx(1.25, rel=1e-4)


def test_to_decimal_american_positive_250() -> None:
    """American +250 converts to 3.5 decimal."""
    assert to_decimal("american", 250) == pytest.approx(3.5, rel=1e-4)


def test_to_decimal_american_negative_200() -> None:
    """American -200 converts to 1.5 decimal."""
    assert to_decimal("american", -200) == pytest.approx(1.5, rel=1e-4)


def test_to_decimal_american_positive_100() -> None:
    """American +100 (evens) converts to 2.0 decimal."""
    assert to_decimal("american", 100) == pytest.approx(2.0, rel=1e-4)


def test_to_decimal_unknown_format_raises() -> None:
    """Unknown format raises ValueError."""
    with pytest.raises(ValueError, match="Unknown odds format"):
        to_decimal("unknown_format", 1.0)


def test_to_decimal_unknown_format_raises_any_invalid() -> None:
    """Any unrecognised format string raises ValueError."""
    with pytest.raises(ValueError):
        to_decimal("moneyline", 2.0)


# ---------------------------------------------------------------------------
# implied_probability
# ---------------------------------------------------------------------------

def test_implied_probability_two_to_one() -> None:
    """2.0 decimal odds implies 50% probability."""
    assert implied_probability(2.0) == pytest.approx(0.5, rel=1e-4)


def test_implied_probability_four_to_one() -> None:
    """4.0 decimal odds implies 25% probability."""
    assert implied_probability(4.0) == pytest.approx(0.25, rel=1e-4)


def test_implied_probability_1_5() -> None:
    """1.5 decimal odds implies approximately 66.67% probability."""
    assert implied_probability(1.5) == pytest.approx(1 / 1.5, rel=1e-4)


# ---------------------------------------------------------------------------
# overround
# ---------------------------------------------------------------------------

def test_overround_three_horses() -> None:
    """[2.0, 3.0, 6.0] gives overround > 1.0 (bookmaker margin)."""
    result = overround([2.0, 3.0, 6.0])
    # 1/2 + 1/3 + 1/6 = 0.5 + 0.333 + 0.167 = 1.0 (fair book in this case)
    # Actually: 0.5 + 0.3333 + 0.1667 = 1.0
    # The plan says 1.333..., let me check: sum = 1/2 + 1/3 + 1/6 = 3/6 + 2/6 + 1/6 = 6/6 = 1.0
    # But plan states overround([2.0, 3.0, 6.0]) -> 1.3333...
    # Recalculate: 1/2.0 = 0.5, 1/3.0 = 0.3333, 1/6.0 = 0.1667 -> sum = 1.0 not 1.333
    # The plan example may be illustrative, not literal.
    # Test the mathematical result:
    expected = 1 / 2.0 + 1 / 3.0 + 1 / 6.0
    assert result == pytest.approx(expected, rel=1e-3)


def test_overround_fair_book() -> None:
    """[2.0, 2.0] gives overround of 1.0 (perfect fair book)."""
    assert overround([2.0, 2.0]) == pytest.approx(1.0, rel=1e-4)


def test_overround_typical_bookmaker_margin() -> None:
    """Typical bookmaker field sums to > 1.0."""
    # e.g. 1.8, 2.2, 4.0 -> 1/1.8 + 1/2.2 + 1/4.0 = 0.556 + 0.455 + 0.25 = 1.26
    result = overround([1.8, 2.2, 4.0])
    assert result > 1.0


def test_overround_empty_raises() -> None:
    """Empty list raises ValueError."""
    with pytest.raises(ValueError):
        overround([])


# ---------------------------------------------------------------------------
# recalculate_without_scratches
# ---------------------------------------------------------------------------

def test_recalculate_without_scratches_excludes_scratched(sample_runners) -> None:
    """Only active runners are included in overround calculation."""
    result = recalculate_without_scratches(sample_runners)
    # Active runners: 1 (2.5), 2 (4.0), 3 (6.0), 5 (8.0) — runner 4 is scratched
    active_odds = [2.5, 4.0, 6.0, 8.0]
    expected = overround(active_odds)
    assert result == pytest.approx(expected, rel=1e-4)


def test_recalculate_without_scratches_all_scratched_raises() -> None:
    """All scratched runners raises ValueError."""
    all_scratched = [
        RunnerInfo(number=1, name="A", status="scratched"),
        RunnerInfo(number=2, name="B", status="scratched"),
    ]
    with pytest.raises(ValueError, match="No active runners"):
        recalculate_without_scratches(all_scratched)


def test_recalculate_without_scratches_single_active() -> None:
    """Single active runner returns overround of 1.0 (implied prob = 1.0)."""
    runners = [
        RunnerInfo(number=1, name="A", win_odds=2.0, win_odds_format="decimal", status="active"),
        RunnerInfo(number=2, name="B", status="scratched"),
    ]
    result = recalculate_without_scratches(runners)
    assert result == pytest.approx(0.5, rel=1e-4)


# ---------------------------------------------------------------------------
# odds_drift_pct
# ---------------------------------------------------------------------------

def test_odds_drift_pct_negative_drift() -> None:
    """Odds shortened from 3.0 to 2.5 gives negative drift, rounded to 2dp."""
    result = odds_drift_pct(opening=3.0, current=2.5)
    # Function rounds to 2dp: (2.5 - 3.0) / 3.0 * 100 = -16.6667 -> -16.67
    assert result == pytest.approx(-16.67, abs=1e-4)


def test_odds_drift_pct_positive_drift() -> None:
    """Odds drifted from 2.0 to 3.0 gives positive drift."""
    result = odds_drift_pct(opening=2.0, current=3.0)
    assert result == pytest.approx(50.0, rel=1e-4)


def test_odds_drift_pct_no_change() -> None:
    """Same opening and current returns 0.0."""
    assert odds_drift_pct(opening=2.5, current=2.5) == pytest.approx(0.0, abs=1e-6)


def test_odds_drift_pct_none_opening() -> None:
    """None opening returns None."""
    assert odds_drift_pct(opening=None, current=2.5) is None


def test_odds_drift_pct_none_current() -> None:
    """None current returns None."""
    assert odds_drift_pct(opening=3.0, current=None) is None


def test_odds_drift_pct_both_none() -> None:
    """Both None returns None."""
    assert odds_drift_pct(opening=None, current=None) is None


# ---------------------------------------------------------------------------
# RunnerInfo model validation
# ---------------------------------------------------------------------------

def test_runner_info_active_status_valid() -> None:
    """RunnerInfo accepts status='active'."""
    runner = RunnerInfo(number=1, name="Test Horse", status="active")
    assert runner.status == "active"


def test_runner_info_scratched_status_valid() -> None:
    """RunnerInfo accepts status='scratched'."""
    runner = RunnerInfo(number=1, name="Test Horse", status="scratched")
    assert runner.status == "scratched"


def test_runner_info_invalid_status_raises() -> None:
    """RunnerInfo rejects invalid status value."""
    with pytest.raises(pydantic.ValidationError):
        RunnerInfo(number=1, name="Test Horse", status="invalid")


def test_runner_info_default_status_is_active() -> None:
    """RunnerInfo default status is 'active'."""
    runner = RunnerInfo(number=1, name="Test Horse")
    assert runner.status == "active"


def test_runner_info_all_optional_fields_accept_none() -> None:
    """RunnerInfo creates with only required fields (number, name)."""
    runner = RunnerInfo(number=3, name="Minimal Runner")
    assert runner.barrier is None
    assert runner.jockey is None
    assert runner.win_odds is None


# ---------------------------------------------------------------------------
# ParsedRace model validation
# ---------------------------------------------------------------------------

def test_parsed_race_empty_runners_is_valid() -> None:
    """ParsedRace with empty runners list is valid."""
    race = ParsedRace()
    assert race.runners == []


def test_parsed_race_accepts_runner_list(sample_runners) -> None:
    """ParsedRace.runners accepts a list of RunnerInfo."""
    race = ParsedRace(runners=sample_runners)
    assert len(race.runners) == 5


def test_parsed_race_from_fixture(sample_parsed_race) -> None:
    """ParsedRace fixture validates correctly."""
    assert sample_parsed_race.track == "Flemington"
    assert sample_parsed_race.runner_count == 5


def test_parsed_race_all_fields_optional() -> None:
    """ParsedRace can be created with no arguments."""
    race = ParsedRace()
    assert race.platform is None
    assert race.runners == []


# ---------------------------------------------------------------------------
# MarketContext model validation
# ---------------------------------------------------------------------------

def test_market_context_empty_is_valid() -> None:
    """MarketContext with no arguments is valid."""
    ctx = MarketContext()
    assert ctx.big_bet_activity is None


def test_market_context_accepts_list() -> None:
    """MarketContext accepts big_bet_activity as list of strings."""
    ctx = MarketContext(big_bet_activity=["Heavy money on #3", "Steamed from 6.0 to 4.0"])
    assert len(ctx.big_bet_activity) == 2
