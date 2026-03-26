"""
Unit tests for EV/Kelly math functions in services/stake/parser/math.py
and pre_skip_check_node in services/stake/pipeline/nodes.py.

TDD RED phase: all tests written before implementation.
Covers all 7 new math functions and the pre_skip_check_node.
"""

import pytest
from unittest.mock import patch, MagicMock

from services.stake.parser.math import (
    no_vig_probability,
    expected_value,
    kelly_fraction,
    bet_size_usdt,
    apply_portfolio_caps,
    apply_sparsity_discount,
    place_bet_ev,
)
from services.stake.pipeline.nodes import pre_skip_check_node


# ---------------------------------------------------------------------------
# no_vig_probability
# ---------------------------------------------------------------------------

class TestNoVigProbability:
    def test_basic_case(self):
        """0.5 / 1.15 = 0.434783"""
        result = no_vig_probability(0.5, 1.15)
        assert abs(result - 0.434783) < 1e-5

    def test_lower_probability(self):
        """0.25 / 1.10 = 0.227273"""
        result = no_vig_probability(0.25, 1.10)
        assert abs(result - 0.227273) < 1e-5

    def test_result_leq_implied_prob(self):
        """Result must be <= implied_prob (removing margin shrinks probability)."""
        for implied in [0.1, 0.3, 0.5, 0.7]:
            result = no_vig_probability(implied, 1.20)
            assert result <= implied

    def test_fair_book_no_change(self):
        """With overround=1.0, no_vig_probability == implied_prob."""
        result = no_vig_probability(0.5, 1.0)
        assert abs(result - 0.5) < 1e-6

    def test_large_overround(self):
        """High overround shrinks probability more."""
        result = no_vig_probability(0.5, 1.50)
        assert abs(result - round(0.5 / 1.50, 6)) < 1e-5

    def test_returns_float(self):
        result = no_vig_probability(0.4, 1.1)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# expected_value
# ---------------------------------------------------------------------------

class TestExpectedValue:
    def test_positive_ev(self):
        """0.5 * 3.0 - 1 = 0.5 (positive EV)."""
        result = expected_value(0.5, 3.0)
        assert abs(result - 0.5) < 1e-6

    def test_negative_ev(self):
        """0.3 * 2.5 - 1 = -0.25 (negative EV)."""
        result = expected_value(0.3, 2.5)
        assert abs(result - (-0.25)) < 1e-6

    def test_zero_probability(self):
        """Zero prob = lose entire stake: 0 * 5 - 1 = -1.0."""
        result = expected_value(0.0, 5.0)
        assert abs(result - (-1.0)) < 1e-6

    def test_breakeven_ev(self):
        """EV = 0 when ai_prob = 1 / decimal_odds."""
        result = expected_value(0.5, 2.0)
        assert abs(result - 0.0) < 1e-6

    def test_high_probability_positive_ev(self):
        """High probability at decent odds = positive EV."""
        result = expected_value(0.8, 2.0)
        assert result > 0

    def test_low_probability_long_odds(self):
        """Very low probability even at long odds can be positive."""
        # 0.1 * 12.0 - 1 = 0.2
        result = expected_value(0.1, 12.0)
        assert abs(result - 0.2) < 1e-6

    def test_returns_float(self):
        result = expected_value(0.5, 2.0)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# kelly_fraction
# ---------------------------------------------------------------------------

class TestKellyFraction:
    def test_basic_positive(self):
        """kelly_fraction(0.5, 3.0) = (0.5 * 2 - 0.5) / 2 = 0.25."""
        result = kelly_fraction(0.5, 3.0)
        assert abs(result - 0.25) < 1e-6

    def test_negative_ev_returns_zero(self):
        """Negative EV should return 0.0 (no bet)."""
        result = kelly_fraction(0.3, 2.5)
        assert result == 0.0

    def test_second_positive(self):
        """kelly_fraction(0.6, 2.0) = (0.6 * 1 - 0.4) / 1 = 0.2."""
        result = kelly_fraction(0.6, 2.0)
        assert abs(result - 0.2) < 1e-6

    def test_never_negative(self):
        """kelly_fraction must never return a negative value."""
        for prob, odds in [(0.1, 1.5), (0.01, 2.0), (0.0, 5.0)]:
            assert kelly_fraction(prob, odds) >= 0.0

    def test_zero_probability_returns_zero(self):
        """Zero probability = no bet."""
        result = kelly_fraction(0.0, 5.0)
        assert result == 0.0

    def test_breakeven_returns_zero(self):
        """Breakeven EV = Kelly fraction of 0."""
        result = kelly_fraction(0.5, 2.0)
        assert result == 0.0

    def test_returns_float(self):
        result = kelly_fraction(0.5, 3.0)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# bet_size_usdt
# ---------------------------------------------------------------------------

class TestBetSizeUsdt:
    def test_basic_quarter_kelly(self):
        """1000 * 0.10 * 0.25 = 25.0 USDT."""
        result = bet_size_usdt(1000, 0.10)
        assert abs(result - 25.0) < 0.01

    def test_cap_at_per_bet_cap(self):
        """1000 * 0.20 * 0.25 = 50.0, capped at 3% = 30.0."""
        result = bet_size_usdt(1000, 0.20)
        assert abs(result - 30.0) < 0.01

    def test_below_min_bet_returns_zero(self):
        """100 * 0.01 * 0.25 = 0.25, below min_bet 1.0 -> return 0.0."""
        result = bet_size_usdt(100, 0.01)
        assert result == 0.0

    def test_full_kelly_still_capped(self):
        """1000 * 0.10 * 1.0 = 100, capped at 3% = 30.0."""
        result = bet_size_usdt(1000, 0.10, kelly_multiplier=1.0)
        assert abs(result - 30.0) < 0.01

    def test_zero_bankroll_returns_zero(self):
        """Zero bankroll = no bet."""
        result = bet_size_usdt(0, 0.10)
        assert result == 0.0

    def test_zero_kelly_returns_zero(self):
        """Zero Kelly fraction = no bet."""
        result = bet_size_usdt(1000, 0.0)
        assert result == 0.0

    def test_custom_params(self):
        """Custom per_bet_cap and min_bet respected."""
        # 500 * 0.10 * 0.25 = 12.5, cap 5% = 25, min 1.0 -> 12.5
        result = bet_size_usdt(500, 0.10, kelly_multiplier=0.25, per_bet_cap_pct=0.05, min_bet=1.0)
        assert abs(result - 12.5) < 0.01

    def test_exactly_at_min_bet(self):
        """Exactly at min_bet boundary should be returned."""
        # Want result = 1.0: bankroll=400, kelly=0.01, multiplier=0.25 -> 400*0.01*0.25=1.0
        result = bet_size_usdt(400, 0.01)
        assert abs(result - 1.0) < 0.01

    def test_returns_rounded_to_two_decimals(self):
        """Result should be rounded to 2 decimal places."""
        result = bet_size_usdt(333, 0.10)
        assert result == round(result, 2)


# ---------------------------------------------------------------------------
# apply_portfolio_caps
# ---------------------------------------------------------------------------

class TestApplyPortfolioCaps:
    def _make_bet(self, bet_type, amount, ev=0.5):
        return {"type": bet_type, "amount": amount, "ev": ev}

    def test_max_win_bets_enforced(self):
        """3 win bets: only first 2 by EV are kept."""
        bets = [
            self._make_bet("win", 10.0, ev=0.3),
            self._make_bet("win", 10.0, ev=0.2),
            self._make_bet("win", 10.0, ev=0.1),
        ]
        result = apply_portfolio_caps(bets, bankroll=1000)
        win_bets = [b for b in result if b["type"] == "win"]
        assert len(win_bets) <= 2

    def test_place_bets_not_counted_against_win_limit(self):
        """Place bets are not counted against max_win_bets."""
        bets = [
            self._make_bet("win", 10.0, ev=0.5),
            self._make_bet("win", 10.0, ev=0.4),
            self._make_bet("place", 10.0, ev=0.3),
        ]
        result = apply_portfolio_caps(bets, bankroll=1000)
        win_bets = [b for b in result if b["type"] == "win"]
        place_bets = [b for b in result if b["type"] == "place"]
        assert len(win_bets) <= 2
        assert len(place_bets) == 1

    def test_total_exposure_cap(self):
        """Total amount does not exceed 5% of bankroll."""
        bets = [
            self._make_bet("win", 30.0, ev=0.5),
            self._make_bet("win", 30.0, ev=0.4),
        ]
        result = apply_portfolio_caps(bets, bankroll=1000)
        total = sum(b["amount"] for b in result)
        assert total <= 1000 * 0.05 + 0.01  # allow tiny float error

    def test_bets_below_min_dropped(self):
        """Bets with amount < 1.0 USDT are dropped."""
        bets = [
            self._make_bet("win", 0.5, ev=0.5),
            self._make_bet("win", 5.0, ev=0.3),
        ]
        result = apply_portfolio_caps(bets, bankroll=1000)
        for b in result:
            assert b["amount"] >= 1.0

    def test_no_mutation_of_input(self):
        """Input list should not be mutated."""
        bets = [self._make_bet("win", 10.0)]
        original_len = len(bets)
        apply_portfolio_caps(bets, bankroll=1000)
        assert len(bets) == original_len

    def test_empty_input_returns_empty(self):
        """Empty input returns empty list."""
        result = apply_portfolio_caps([], bankroll=1000)
        assert result == []

    def test_win_bets_sorted_by_ev_descending(self):
        """Best EV win bets kept when over limit."""
        bets = [
            self._make_bet("win", 10.0, ev=0.1),
            self._make_bet("win", 10.0, ev=0.5),
            self._make_bet("win", 10.0, ev=0.3),
        ]
        result = apply_portfolio_caps(bets, bankroll=10000)
        win_bets = [b for b in result if b["type"] == "win"]
        if len(win_bets) == 2:
            evs = [b["ev"] for b in win_bets]
            assert 0.5 in evs
            assert 0.3 in evs

    def test_returns_new_list(self):
        """Returns a new list object."""
        bets = [self._make_bet("win", 10.0)]
        result = apply_portfolio_caps(bets, bankroll=1000)
        assert result is not bets


# ---------------------------------------------------------------------------
# apply_sparsity_discount
# ---------------------------------------------------------------------------

class TestApplySparsityDiscount:
    def test_sparse_data_halves_amount(self):
        """apply_sparsity_discount(10.0, True) = 5.0."""
        result = apply_sparsity_discount(10.0, True)
        assert abs(result - 5.0) < 0.01

    def test_not_sparse_unchanged(self):
        """apply_sparsity_discount(10.0, False) = 10.0."""
        result = apply_sparsity_discount(10.0, False)
        assert abs(result - 10.0) < 0.01

    def test_below_min_after_discount_returns_zero(self):
        """1.5 * 0.5 = 0.75 < 1.0 min_bet -> return 0.0."""
        result = apply_sparsity_discount(1.5, True)
        assert result == 0.0

    def test_exactly_at_min_after_discount(self):
        """2.0 * 0.5 = 1.0 = min_bet -> return 1.0."""
        result = apply_sparsity_discount(2.0, True)
        assert abs(result - 1.0) < 0.01

    def test_custom_discount(self):
        """Custom discount factor."""
        result = apply_sparsity_discount(10.0, True, discount=0.3)
        assert abs(result - 3.0) < 0.01

    def test_returns_float(self):
        result = apply_sparsity_discount(5.0, False)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# place_bet_ev
# ---------------------------------------------------------------------------

class TestPlaceBetEv:
    def test_positive_ev(self):
        """place_bet_ev(0.7, 2.0) = 0.7 * 1.0 - 0.3 = 0.4."""
        result = place_bet_ev(0.7, 2.0)
        assert abs(result - 0.4) < 1e-6

    def test_negative_ev(self):
        """place_bet_ev(0.3, 1.5) = 0.3 * 0.5 - 0.7 = -0.55."""
        result = place_bet_ev(0.3, 1.5)
        assert abs(result - (-0.55)) < 1e-6

    def test_uses_place_odds(self):
        """Verifies calculation uses place_odds (not win_odds semantics)."""
        # If place_odds=1.5, net = (1.5-1) = 0.5
        # EV = prob * 0.5 - (1-prob)
        result = place_bet_ev(0.8, 1.5)
        expected = 0.8 * (1.5 - 1) - 0.2
        assert abs(result - expected) < 1e-6

    def test_breakeven(self):
        """place_bet_ev(0.5, 2.0) = 0.5 * 1.0 - 0.5 = 0.0."""
        result = place_bet_ev(0.5, 2.0)
        assert abs(result - 0.0) < 1e-6

    def test_zero_probability(self):
        """Zero probability = lose entire stake."""
        result = place_bet_ev(0.0, 3.0)
        expected = 0.0 * (3.0 - 1) - 1.0
        assert abs(result - expected) < 1e-6

    def test_returns_float(self):
        result = place_bet_ev(0.5, 2.0)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# pre_skip_check_node
# ---------------------------------------------------------------------------

class TestPreSkipCheckNode:
    def test_high_overround_sets_skip_signal(self):
        """overround_active=1.20 (margin 20%) > threshold 15% -> skip."""
        state = {"overround_active": 1.20}
        result = pre_skip_check_node(state)
        assert result.get("skip_signal") is True
        assert "skip_reason" in result
        assert result.get("skip_tier") == 1

    def test_low_overround_no_skip(self):
        """overround_active=1.10 (margin 10%) < threshold 15% -> no skip."""
        state = {"overround_active": 1.10}
        result = pre_skip_check_node(state)
        assert result.get("skip_signal") is False

    def test_no_overround_returns_empty(self):
        """overround_active=None -> no skip decision (return {})."""
        state = {"overround_active": None}
        result = pre_skip_check_node(state)
        assert result == {}

    def test_missing_overround_returns_empty(self):
        """overround_active missing from state -> no skip decision."""
        state = {}
        result = pre_skip_check_node(state)
        assert result == {}

    def test_exactly_at_threshold_no_skip(self):
        """overround_active=1.15 (margin exactly 15%) should NOT trigger skip (< not <=)."""
        state = {"overround_active": 1.15}
        result = pre_skip_check_node(state)
        # At exactly threshold, depends on implementation (> vs >=); plan says "margin > threshold"
        # So exactly 15% should not skip
        assert result.get("skip_signal") is not True

    def test_skip_reason_is_string(self):
        """skip_reason should be a non-empty string."""
        state = {"overround_active": 1.25}
        result = pre_skip_check_node(state)
        assert isinstance(result.get("skip_reason"), str)
        assert len(result["skip_reason"]) > 0

    def test_returns_dict(self):
        """Result is always a dict."""
        assert isinstance(pre_skip_check_node({}), dict)
        assert isinstance(pre_skip_check_node({"overround_active": 1.5}), dict)
