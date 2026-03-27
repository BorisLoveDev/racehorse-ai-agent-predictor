"""
Tests for Phase 3 results evaluation: evaluate_bets(), BetOutcome model,
ParsedResult model, BetOutcomesRepository, and BankrollRepository extensions.
"""

import os
import tempfile
import pytest

from services.stake.results.models import ParsedResult, BetOutcome, LessonEntry
from services.stake.results.evaluator import evaluate_bets
from services.stake.results.repository import BetOutcomesRepository
from services.stake.bankroll.repository import BankrollRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def win_bet():
    """Sample win bet dict matching sizing_node output format with odds fields."""
    return {
        "runner_name": "Thunder",
        "runner_number": 3,
        "bet_type": "win",
        "usdt_amount": 5.0,
        "decimal_odds": 3.5,
        "place_odds": None,
        "ev": 0.12,
        "kelly_pct": 2.1,
        "label": "best_value",
        "data_sparse": False,
        "reasoning": "Strong form",
    }


@pytest.fixture
def place_bet():
    """Sample place bet dict with place_odds set."""
    return {
        "runner_name": "Lightning",
        "runner_number": 5,
        "bet_type": "place",
        "usdt_amount": 3.0,
        "decimal_odds": 2.5,
        "place_odds": 1.8,
        "ev": 0.08,
        "kelly_pct": 1.5,
        "label": "best_place_candidate",
        "data_sparse": False,
        "reasoning": "Good place form",
    }


@pytest.fixture
def full_result():
    """Full race result with finishing order [3, 5, 11]."""
    return ParsedResult(
        finishing_order=[3, 5, 11],
        is_partial=False,
        confidence="high",
    )


@pytest.fixture
def partial_result():
    """Partial result with only winner known."""
    return ParsedResult(
        finishing_order=[3],
        is_partial=True,
        confidence="low",
    )


# ---------------------------------------------------------------------------
# ParsedResult model tests
# ---------------------------------------------------------------------------


def test_parsed_result_full():
    """ParsedResult model accepts finishing_order=[3,5,11], is_partial=False."""
    result = ParsedResult(
        finishing_order=[3, 5, 11],
        is_partial=False,
        confidence="high",
    )
    assert result.finishing_order == [3, 5, 11]
    assert result.is_partial is False
    assert result.confidence == "high"


def test_parsed_result_partial():
    """ParsedResult model with finishing_order=[3] and is_partial=True."""
    result = ParsedResult(
        finishing_order=[3],
        is_partial=True,
        confidence="low",
    )
    assert result.finishing_order == [3]
    assert result.is_partial is True


def test_parsed_result_defaults():
    """ParsedResult model has sensible defaults."""
    result = ParsedResult()
    assert result.finishing_order == []
    assert result.is_partial is False
    assert result.confidence == "high"
    assert result.raw_text == ""


# ---------------------------------------------------------------------------
# BetOutcome model tests
# ---------------------------------------------------------------------------


def test_bet_outcome_required_fields():
    """BetOutcome model has all required fields."""
    outcome = BetOutcome(
        runner_number=3,
        runner_name="Thunder",
        bet_type="win",
        amount_usdt=5.0,
        won=True,
        profit_usdt=12.5,
        evaluable=True,
    )
    assert outcome.runner_number == 3
    assert outcome.runner_name == "Thunder"
    assert outcome.bet_type == "win"
    assert outcome.amount_usdt == 5.0
    assert outcome.won is True
    assert outcome.profit_usdt == 12.5
    assert outcome.evaluable is True


def test_bet_outcome_defaults():
    """BetOutcome defaults to won=False, evaluable=True."""
    outcome = BetOutcome(
        runner_name="Runner",
        bet_type="win",
        amount_usdt=5.0,
    )
    assert outcome.won is False
    assert outcome.evaluable is True
    assert outcome.profit_usdt == 0.0


# ---------------------------------------------------------------------------
# LessonEntry model tests
# ---------------------------------------------------------------------------


def test_lesson_entry_model():
    """LessonEntry model validates correctly."""
    lesson = LessonEntry(
        error_tag="overconfidence_on_short_odds",
        rule_sentence="Never bet more than 2% on odds under 1.5",
        is_failure_mode=True,
    )
    assert lesson.error_tag == "overconfidence_on_short_odds"
    assert lesson.is_failure_mode is True


# ---------------------------------------------------------------------------
# evaluate_bets() tests
# ---------------------------------------------------------------------------


def test_evaluate_win_bet_winner(win_bet, full_result):
    """Win bet on runner #3 who won -> profit = amount * decimal_odds - amount."""
    outcomes = evaluate_bets([win_bet], full_result)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.won is True
    assert outcome.evaluable is True
    expected_profit = round(5.0 * 3.5 - 5.0, 4)
    assert outcome.profit_usdt == expected_profit  # 12.5


def test_evaluate_win_bet_loser(full_result):
    """Win bet on runner #3 who lost -> profit = -amount."""
    bet = {
        "runner_name": "Loser",
        "runner_number": 7,
        "bet_type": "win",
        "usdt_amount": 5.0,
        "decimal_odds": 3.5,
        "place_odds": None,
    }
    outcomes = evaluate_bets([bet], full_result)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.won is False
    assert outcome.evaluable is True
    assert outcome.profit_usdt == -5.0


def test_evaluate_place_bet_in_top3(place_bet, full_result):
    """Place bet on runner in top 3 (full result) -> profit = amount * place_odds - amount."""
    # Runner #5 is in finishing_order=[3, 5, 11], so it placed
    outcomes = evaluate_bets([place_bet], full_result)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.won is True
    assert outcome.evaluable is True
    expected_profit = round(3.0 * 1.8 - 3.0, 4)
    assert outcome.profit_usdt == expected_profit  # 2.4


def test_evaluate_place_bet_not_in_top3(full_result):
    """Place bet on runner not in top 3 -> profit = -amount."""
    bet = {
        "runner_name": "BackOfField",
        "runner_number": 9,
        "bet_type": "place",
        "usdt_amount": 3.0,
        "decimal_odds": 4.0,
        "place_odds": 1.5,
    }
    outcomes = evaluate_bets([bet], full_result)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.won is False
    assert outcome.profit_usdt == -3.0


def test_evaluate_place_bet_partial_result(place_bet, partial_result):
    """Place bet when is_partial=True -> evaluable=False, profit=0."""
    outcomes = evaluate_bets([place_bet], partial_result)
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.evaluable is False
    assert outcome.won is False
    assert outcome.profit_usdt == 0.0


def test_evaluate_mixed_partial_result(win_bet, place_bet, partial_result):
    """Partial result: win bet is evaluable, place bet is not evaluable."""
    # partial_result has finishing_order=[3] (winner = 3)
    # win_bet is for runner #3 (the winner), place_bet for runner #5
    outcomes = evaluate_bets([win_bet, place_bet], partial_result)
    assert len(outcomes) == 2

    win_outcome = next(o for o in outcomes if o.bet_type == "win")
    place_outcome = next(o for o in outcomes if o.bet_type == "place")

    assert win_outcome.evaluable is True
    assert win_outcome.won is True  # runner #3 won

    assert place_outcome.evaluable is False
    assert place_outcome.won is False


def test_evaluate_no_place_odds_not_evaluable(full_result):
    """Place bet without place_odds -> evaluable=False."""
    bet = {
        "runner_name": "NoPlaceOdds",
        "runner_number": 3,
        "bet_type": "place",
        "usdt_amount": 5.0,
        "decimal_odds": 3.0,
        "place_odds": None,
    }
    outcomes = evaluate_bets([bet], full_result)
    assert len(outcomes) == 1
    assert outcomes[0].evaluable is False


def test_evaluate_profit_rounded_to_4_places():
    """evaluate_bets rounds profit to 4 decimal places."""
    bet = {
        "runner_name": "OddsRunner",
        "runner_number": 1,
        "bet_type": "win",
        "usdt_amount": 3.0,
        "decimal_odds": 2.3,
        "place_odds": None,
    }
    result = ParsedResult(finishing_order=[1], is_partial=False)
    outcomes = evaluate_bets([bet], result)
    assert outcomes[0].profit_usdt == round(3.0 * 2.3 - 3.0, 4)


# ---------------------------------------------------------------------------
# BetOutcomesRepository tests
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary SQLite db path."""
    return str(tmp_path / "test.db")


@pytest.fixture
def outcomes_repo(tmp_db):
    return BetOutcomesRepository(db_path=tmp_db)


@pytest.fixture
def sample_outcomes():
    """Two bet outcome dicts — one win (won), one place (lost)."""
    return [
        {
            "runner_name": "Thunder",
            "runner_number": 3,
            "bet_type": "win",
            "amount_usdt": 5.0,
            "decimal_odds": 3.5,
            "place_odds": None,
            "won": True,
            "profit_usdt": 12.5,
            "evaluable": True,
        },
        {
            "runner_name": "Lightning",
            "runner_number": 5,
            "bet_type": "place",
            "amount_usdt": 3.0,
            "decimal_odds": 2.5,
            "place_odds": 1.8,
            "won": False,
            "profit_usdt": -3.0,
            "evaluable": True,
        },
    ]


def test_bet_outcomes_save_and_count(outcomes_repo, sample_outcomes):
    """BetOutcomesRepository.save_outcomes inserts correct row count."""
    outcomes_repo.save_outcomes(run_id=1, is_placed=True, outcomes=sample_outcomes)
    stats = outcomes_repo.get_total_stats(placed_only=True)
    assert stats["total_bets"] == 2


def test_bet_outcomes_get_total_stats(outcomes_repo, sample_outcomes):
    """get_total_stats returns correct aggregation for placed-only bets."""
    outcomes_repo.save_outcomes(run_id=1, is_placed=True, outcomes=sample_outcomes)
    stats = outcomes_repo.get_total_stats(placed_only=True)
    assert stats["total_bets"] == 2
    assert stats["wins"] == 1
    assert stats["win_rate"] == 50.0
    # total profit = 12.5 + (-3.0) = 9.5
    assert stats["total_profit_usdt"] == 9.5


def test_bet_outcomes_placed_filter(outcomes_repo, sample_outcomes):
    """placed_only=True excludes tracked-only bets (is_placed=0)."""
    # Save as tracked only (is_placed=False)
    outcomes_repo.save_outcomes(run_id=1, is_placed=False, outcomes=sample_outcomes)
    stats_placed = outcomes_repo.get_total_stats(placed_only=True)
    stats_all = outcomes_repo.get_total_stats(placed_only=False)
    assert stats_placed["total_bets"] == 0
    assert stats_all["total_bets"] == 2


def test_bet_outcomes_period_stats(outcomes_repo, sample_outcomes):
    """get_period_stats with days=7 includes today's bets."""
    outcomes_repo.save_outcomes(run_id=1, is_placed=True, outcomes=sample_outcomes)
    stats = outcomes_repo.get_period_stats(days=7, placed_only=True)
    assert stats["total_bets"] == 2


def test_bet_outcomes_empty_stats(outcomes_repo):
    """get_total_stats returns zeros when no bets saved."""
    stats = outcomes_repo.get_total_stats()
    assert stats["total_bets"] == 0
    assert stats["win_rate"] == 0.0


# ---------------------------------------------------------------------------
# BankrollRepository peak/drawdown tests
# ---------------------------------------------------------------------------


@pytest.fixture
def bankroll_repo(tmp_db):
    repo = BankrollRepository(db_path=tmp_db)
    return repo


def test_peak_balance_none_initially(bankroll_repo):
    """get_peak_balance returns None before any balance is set."""
    bankroll_repo.set_balance(100.0)
    # After set_balance, peak should be initialised
    peak = bankroll_repo.get_peak_balance()
    assert peak == 100.0


def test_update_peak_if_higher(bankroll_repo):
    """update_peak_if_higher tracks the maximum balance."""
    bankroll_repo.set_balance(100.0)
    bankroll_repo.update_peak_if_higher(150.0)
    assert bankroll_repo.get_peak_balance() == 150.0
    # Lower value does not change peak
    bankroll_repo.update_peak_if_higher(80.0)
    assert bankroll_repo.get_peak_balance() == 150.0


def test_set_balance_updates_peak(bankroll_repo):
    """set_balance auto-updates peak when new balance is higher."""
    bankroll_repo.set_balance(100.0)
    bankroll_repo.set_balance(200.0)
    assert bankroll_repo.get_peak_balance() == 200.0


def test_drawdown_unlocked_persistence(bankroll_repo):
    """drawdown_unlocked flag persists across method calls."""
    bankroll_repo.set_balance(100.0)
    assert bankroll_repo.is_drawdown_unlocked() is False
    bankroll_repo.set_drawdown_unlocked(True)
    assert bankroll_repo.is_drawdown_unlocked() is True
    bankroll_repo.set_drawdown_unlocked(False)
    assert bankroll_repo.is_drawdown_unlocked() is False


def test_check_and_auto_reset_drawdown(bankroll_repo):
    """check_and_auto_reset_drawdown resets flag when balance recovers."""
    bankroll_repo.set_balance(100.0)
    # Simulate drawdown: balance drops to 75 (25% from peak of 100)
    # First set peak manually via update_peak_if_higher
    bankroll_repo.set_drawdown_unlocked(True)
    # Set balance below threshold (20% from peak = 80)
    bankroll_repo.set_balance(75.0)
    # At this point, peak is 100, balance is 75 => 25% drawdown
    # check_and_auto_reset: threshold 20% => recovery point = 80; 75 < 80 => no reset
    bankroll_repo.check_and_auto_reset_drawdown(threshold_pct=20.0)
    assert bankroll_repo.is_drawdown_unlocked() is True  # still unlocked

    # Recover above threshold
    bankroll_repo.set_balance(90.0)  # 10% from peak of 100, above 20% threshold
    bankroll_repo.check_and_auto_reset_drawdown(threshold_pct=20.0)
    assert bankroll_repo.is_drawdown_unlocked() is False  # auto-reset
