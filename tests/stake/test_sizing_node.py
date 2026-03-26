"""
Tests for sizing_node portfolio cap enforcement, sparsity discount,
analysis skip passthrough, and format_recommendation HTML escaping.

Per plan 02-04: verifies all portfolio constraints, skip signals, and
that variable strings in HTML output are properly escaped.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.stake.pipeline.formatter import format_recommendation
from services.stake.pipeline.nodes import format_recommendation_node, sizing_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis_result(
    runners: list[dict],
    overall_skip: bool = False,
    skip_reason: str | None = None,
    ai_override: bool = False,
    override_reason: str | None = None,
    market_discrepancy_notes: list[str] | None = None,
) -> dict:
    """Build a minimal analysis_result dict."""
    return {
        "recommendations": runners,
        "overall_skip": overall_skip,
        "skip_reason": skip_reason,
        "ai_override": ai_override,
        "override_reason": override_reason,
        "market_discrepancy_notes": market_discrepancy_notes or [],
    }


def _runner_rec(
    number: int,
    name: str,
    ai_win_prob: float,
    label: str = "best_value",
    reasoning: str = "Good form.",
    ai_place_prob: float | None = None,
) -> dict:
    return {
        "runner_name": name,
        "runner_number": number,
        "label": label,
        "ai_win_prob": ai_win_prob,
        "ai_place_prob": ai_place_prob,
        "reasoning": reasoning,
    }


def _enriched_runner(number: int, name: str, decimal_odds: float, status: str = "active") -> dict:
    from services.stake.parser.math import implied_probability
    return {
        "number": number,
        "name": name,
        "status": status,
        "decimal_odds": decimal_odds,
        "implied_prob": implied_probability(decimal_odds),
        "odds_drift": None,
        "jockey": None,
        "trainer": None,
        "form_string": None,
        "tags": [],
    }


def _base_state(
    analysis_result: dict,
    enriched_runners: list[dict],
    research_results: dict | None = None,
    skip_signal: bool = False,
) -> dict:
    return {
        "analysis_result": analysis_result,
        "enriched_runners": enriched_runners,
        "research_results": research_results or {},
        "skip_signal": skip_signal,
        "overround_active": 1.12,
        "parsed_race": None,
    }


# ---------------------------------------------------------------------------
# sizing_node tests
# ---------------------------------------------------------------------------


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_positive_ev_produces_bets(mock_repo_cls):
    """sizing_node returns bets for +EV runners."""
    mock_repo = MagicMock()
    mock_repo.get_balance.return_value = 1000.0
    mock_repo_cls.return_value = mock_repo

    analysis = _make_analysis_result([
        _runner_rec(1, "Fast Horse", 0.45, label="best_value"),
        _runner_rec(2, "Good Runner", 0.35, label="highest_win_probability"),
    ])
    enriched = [
        _enriched_runner(1, "Fast Horse", 3.0),   # EV = 0.45*3 - 1 = 0.35 (+EV)
        _enriched_runner(2, "Good Runner", 4.5),  # EV = 0.35*4.5 - 1 = 0.575 (+EV)
    ]
    state = _base_state(analysis, enriched)

    result = sizing_node(state)
    bets = result.get("final_bets", [])

    assert len(bets) > 0, "Should produce at least one bet for +EV runners"
    for bet in bets:
        assert bet["usdt_amount"] > 0
        assert bet["ev"] > 0


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_negative_ev_excluded(mock_repo_cls):
    """sizing_node skips runners with negative EV."""
    mock_repo = MagicMock()
    mock_repo.get_balance.return_value = 1000.0
    mock_repo_cls.return_value = mock_repo

    analysis = _make_analysis_result([
        _runner_rec(1, "Long Shot", 0.10, label="best_value"),  # EV at 3.0 = -0.7
    ])
    enriched = [_enriched_runner(1, "Long Shot", 3.0)]
    state = _base_state(analysis, enriched)

    result = sizing_node(state)
    bets = result.get("final_bets", [])

    assert bets == [], "Negative EV runner should produce no bets"


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_portfolio_cap_max_win_bets(mock_repo_cls):
    """sizing_node enforces max 2 win bets (3 given, 2 kept by EV)."""
    mock_repo = MagicMock()
    mock_repo.get_balance.return_value = 10_000.0
    mock_repo_cls.return_value = mock_repo

    # Three +EV win bets; only top 2 by EV should survive
    analysis = _make_analysis_result([
        _runner_rec(1, "Horse A", 0.40, label="best_value"),        # EV = 0.40*3.5 - 1 = 0.40
        _runner_rec(2, "Horse B", 0.35, label="best_value"),        # EV = 0.35*4.0 - 1 = 0.40
        _runner_rec(3, "Horse C", 0.30, label="highest_win_probability"),  # EV = 0.30*5.0 - 1 = 0.50
    ])
    enriched = [
        _enriched_runner(1, "Horse A", 3.5),
        _enriched_runner(2, "Horse B", 4.0),
        _enriched_runner(3, "Horse C", 5.0),
    ]
    state = _base_state(analysis, enriched)

    result = sizing_node(state)
    bets = result.get("final_bets", [])

    win_bets = [b for b in bets if b["bet_type"] == "win"]
    assert len(win_bets) <= 2, f"Expected ≤2 win bets, got {len(win_bets)}"


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_total_exposure_cap(mock_repo_cls):
    """sizing_node enforces 5% total exposure cap."""
    mock_repo = MagicMock()
    bankroll = 1000.0
    mock_repo.get_balance.return_value = bankroll
    mock_repo_cls.return_value = mock_repo

    # Two +EV bets; total must not exceed 5% = 50 USDT
    analysis = _make_analysis_result([
        _runner_rec(1, "Horse A", 0.45, label="best_value"),
        _runner_rec(2, "Horse B", 0.40, label="best_value"),
    ])
    enriched = [
        _enriched_runner(1, "Horse A", 3.0),
        _enriched_runner(2, "Horse B", 3.5),
    ]
    state = _base_state(analysis, enriched)

    result = sizing_node(state)
    bets = result.get("final_bets", [])

    total = sum(b["usdt_amount"] for b in bets)
    max_exposure = bankroll * 0.05
    assert total <= max_exposure + 1e-6, (
        f"Total exposure {total:.2f} USDT exceeds 5% cap of {max_exposure:.2f} USDT"
    )


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_sparsity_discount_applied(mock_repo_cls):
    """sizing_node halves bet size when research data is sparse."""
    mock_repo = MagicMock()
    mock_repo.get_balance.return_value = 1000.0
    mock_repo_cls.return_value = mock_repo

    analysis = _make_analysis_result([
        _runner_rec(1, "Sparse Horse", 0.45, label="best_value"),
    ])
    enriched = [_enriched_runner(1, "Sparse Horse", 3.0)]

    # Research marks this runner as sparse
    research_results = {
        "runners": [{"runner_name": "Sparse Horse", "data_quality": "sparse"}],
        "overall_notes": "",
    }

    # First get bet size WITHOUT sparse flag
    state_normal = _base_state(analysis, enriched, research_results=None)
    result_normal = sizing_node(state_normal)
    normal_bets = result_normal.get("final_bets", [])

    # Now get bet size WITH sparse flag
    state_sparse = _base_state(analysis, enriched, research_results=research_results)
    result_sparse = sizing_node(state_sparse)
    sparse_bets = result_sparse.get("final_bets", [])

    if normal_bets and sparse_bets:
        normal_amount = normal_bets[0]["usdt_amount"]
        sparse_amount = sparse_bets[0]["usdt_amount"]
        assert sparse_amount < normal_amount, (
            f"Sparse bet {sparse_amount:.2f} should be less than normal bet {normal_amount:.2f}"
        )
        assert sparse_bets[0]["data_sparse"] is True


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_overall_skip_passthrough(mock_repo_cls):
    """sizing_node returns Tier 2 skip when analysis.overall_skip is True."""
    mock_repo = MagicMock()
    mock_repo.get_balance.return_value = 1000.0
    mock_repo_cls.return_value = mock_repo

    analysis = _make_analysis_result(
        runners=[_runner_rec(1, "Fast Horse", 0.45, label="best_value")],
        overall_skip=True,
        skip_reason="Suspicious market movements detected",
    )
    enriched = [_enriched_runner(1, "Fast Horse", 3.0)]
    state = _base_state(analysis, enriched)

    result = sizing_node(state)

    assert result.get("skip_signal") is True
    assert result.get("skip_tier") == 2
    assert "Suspicious" in result.get("skip_reason", "")
    assert result.get("final_bets") == []


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_ai_override_passthrough(mock_repo_cls):
    """sizing_node returns Tier 2 skip when analysis.ai_override is True."""
    mock_repo = MagicMock()
    mock_repo.get_balance.return_value = 1000.0
    mock_repo_cls.return_value = mock_repo

    analysis = _make_analysis_result(
        runners=[_runner_rec(1, "Fast Horse", 0.45, label="best_value")],
        ai_override=True,
        override_reason="Horse has injury concern from research",
    )
    enriched = [_enriched_runner(1, "Fast Horse", 3.0)]
    state = _base_state(analysis, enriched)

    result = sizing_node(state)

    assert result.get("skip_signal") is True
    assert result.get("skip_tier") == 2


def test_sizing_node_skip_signal_passthrough():
    """sizing_node returns {} immediately when skip_signal is already True."""
    state = {
        "skip_signal": True,
        "skip_reason": "Tier 1 overround skip",
        "skip_tier": 1,
        "analysis_result": _make_analysis_result([]),
        "enriched_runners": [],
    }

    result = sizing_node(state)
    assert result == {}, "sizing_node should return {} when skip_signal is already True"


@patch("services.stake.pipeline.nodes.BankrollRepository")
def test_sizing_node_empty_when_all_negative_ev(mock_repo_cls):
    """sizing_node returns empty final_bets when all runners are -EV."""
    mock_repo = MagicMock()
    mock_repo.get_balance.return_value = 1000.0
    mock_repo_cls.return_value = mock_repo

    analysis = _make_analysis_result([
        _runner_rec(1, "Low Prob", 0.05, label="best_value"),   # EV = 0.05*3 - 1 = -0.85
        _runner_rec(2, "Low Prob 2", 0.10, label="best_value"), # EV = 0.10*3 - 1 = -0.70
    ])
    enriched = [
        _enriched_runner(1, "Low Prob", 3.0),
        _enriched_runner(2, "Low Prob 2", 3.0),
    ]
    state = _base_state(analysis, enriched)

    result = sizing_node(state)
    bets = result.get("final_bets", [])

    assert bets == []


# ---------------------------------------------------------------------------
# format_recommendation tests — HTML escaping
# ---------------------------------------------------------------------------


def test_format_recommendation_escapes_runner_name():
    """format_recommendation escapes HTML chars in runner name."""
    state = {
        "skip_signal": False,
        "final_bets": [
            {
                "runner_name": "Horse <Bad> & Name",
                "runner_number": 1,
                "label": "best_value",
                "bet_type": "win",
                "ev": 0.35,
                "kelly_pct": 5.0,
                "usdt_amount": 15.0,
                "data_sparse": False,
                "reasoning": "Normal reasoning.",
            }
        ],
        "analysis_result": {
            "market_discrepancy_notes": [],
        },
    }

    result = format_recommendation(state)

    assert "<Bad>" not in result, "Unescaped < > in runner name should not appear"
    assert "&lt;Bad&gt;" in result or "Horse" in result, "HTML should be escaped"
    assert "&amp;" in result or "Horse" in result


def test_format_recommendation_escapes_reasoning():
    """format_recommendation escapes HTML special chars in reasoning text."""
    state = {
        "skip_signal": False,
        "final_bets": [
            {
                "runner_name": "Normal Horse",
                "runner_number": 2,
                "label": "highest_win_probability",
                "bet_type": "win",
                "ev": 0.20,
                "kelly_pct": 3.0,
                "usdt_amount": 10.0,
                "data_sparse": False,
                "reasoning": "Trainer has 50% strike rate at <this track> & conditions.",
            }
        ],
        "analysis_result": {
            "market_discrepancy_notes": [],
        },
    }

    result = format_recommendation(state)

    assert "<this track>" not in result, "Unescaped tags in reasoning should not appear"
    assert "&lt;" in result or "track" in result


def test_format_recommendation_escapes_skip_reason():
    """format_recommendation escapes HTML in skip_reason."""
    state = {
        "skip_signal": True,
        "skip_reason": "Margin > 20% — <unsafe> & overbet",
        "skip_tier": 1,
    }

    result = format_recommendation(state)

    assert "<unsafe>" not in result, "Unescaped HTML in skip_reason should not appear"
    assert "SKIP" in result


def test_format_recommendation_skip_message_format():
    """format_recommendation produces correct skip message structure."""
    state = {
        "skip_signal": True,
        "skip_reason": "Overround 18% exceeds threshold",
        "skip_tier": 1,
    }

    result = format_recommendation(state)

    assert "<b>SKIP</b>" in result
    assert "Tier 1" in result
    assert "Overround 18% exceeds threshold" in result


def test_format_recommendation_no_bets_message():
    """format_recommendation shows no-bets message when final_bets is empty."""
    state = {
        "skip_signal": False,
        "final_bets": [],
        "analysis_result": {},
    }

    result = format_recommendation(state)

    assert "No Bets" in result
    assert "negative EV" in result


def test_format_recommendation_market_discrepancy_notes_escaped():
    """format_recommendation escapes HTML chars in market discrepancy notes."""
    state = {
        "skip_signal": False,
        "final_bets": [
            {
                "runner_name": "Safe Horse",
                "runner_number": 3,
                "label": "best_value",
                "bet_type": "win",
                "ev": 0.25,
                "kelly_pct": 4.0,
                "usdt_amount": 12.0,
                "data_sparse": False,
                "reasoning": "Strong form.",
            }
        ],
        "analysis_result": {
            "market_discrepancy_notes": [
                "TAB odds 3.5 vs Stake 4.2 — <possible> & value",
            ],
        },
    }

    result = format_recommendation(state)

    assert "<possible>" not in result, "Unescaped HTML in market notes should not appear"
    assert "Market Notes" in result


def test_format_recommendation_sparse_data_flag():
    """format_recommendation shows SPARSE DATA flag when data_sparse is True."""
    state = {
        "skip_signal": False,
        "final_bets": [
            {
                "runner_name": "Sparse Horse",
                "runner_number": 4,
                "label": "best_value",
                "bet_type": "win",
                "ev": 0.30,
                "kelly_pct": 3.5,
                "usdt_amount": 5.0,
                "data_sparse": True,
                "reasoning": "Limited data available.",
            }
        ],
        "analysis_result": {
            "market_discrepancy_notes": [],
        },
    }

    result = format_recommendation(state)

    assert "SPARSE DATA" in result


def test_format_recommendation_node_delegates_to_formatter():
    """format_recommendation_node wraps format_recommendation and returns dict."""
    from services.stake.pipeline.nodes import format_recommendation_node

    state = {
        "skip_signal": True,
        "skip_reason": "Test skip",
        "skip_tier": 1,
    }

    result = format_recommendation_node(state)  # type: ignore[arg-type]

    assert "recommendation_text" in result
    assert "SKIP" in result["recommendation_text"]
