"""Hotfix tests:
- Exotic bet suggestions surface in both recommendation card and no-bets card.
- report_result keyboard callback routes to awaiting_result for calibration.
- skip_result callback dismisses cleanly to idle.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.stake.analysis.models import AnalysisResult, RunnerAnalysis
from services.stake.callbacks import TrackingCB
from services.stake.handlers.results import handle_tracking_choice
from services.stake.keyboards.stake_kb import report_result_kb
from services.stake.pipeline.formatter import format_recommendation
from services.stake.states import PipelineStates


# --- exotic_suggestions on the model ----------------------------------------

def test_analysis_result_exotic_suggestions_default_empty():
    ar = AnalysisResult(
        recommendations=[],
        overall_skip=False,
        ai_override=False,
    )
    assert ar.exotic_suggestions == []


def test_analysis_result_accepts_exotic_suggestions():
    ar = AnalysisResult(
        recommendations=[],
        overall_skip=False,
        ai_override=False,
        exotic_suggestions=[
            "Trifecta box 3-7-9: top-3 AI probs cluster tightly.",
            "Exacta 3>7: favourite dominant, #7 clear second pick.",
        ],
    )
    assert len(ar.exotic_suggestions) == 2


# --- formatter: exotics in no-bets card -------------------------------------

def test_no_bets_card_includes_exotic_ideas():
    state = {
        "skip_signal": False,
        "final_bets": [],
        "enriched_runners": [],
        "analysis_result": {
            "recommendations": [
                {
                    "runner_name": "Swift", "runner_number": 3,
                    "label": "highest_win_probability",
                    "ai_win_prob": 0.4, "reasoning": "good",
                },
            ],
            "exotic_suggestions": [
                "QPS 3 with 5,7: safe place cover.",
                "Trifecta box 3-5-7: tight top group.",
            ],
        },
    }
    result = format_recommendation(state)
    assert "Exotic Ideas" in result
    assert "QPS 3 with 5,7" in result
    assert "Trifecta box 3-5-7" in result


def test_no_bets_card_escapes_exotic_html():
    state = {
        "skip_signal": False,
        "final_bets": [],
        "enriched_runners": [],
        "analysis_result": {
            "exotic_suggestions": ["<bad>exacta</bad>"],
        },
    }
    result = format_recommendation(state)
    assert "<bad>" not in result
    assert "&lt;bad&gt;" in result


def test_no_bets_card_skips_exotic_section_when_empty():
    state = {
        "skip_signal": False,
        "final_bets": [],
        "enriched_runners": [],
        "analysis_result": {"exotic_suggestions": []},
    }
    result = format_recommendation(state)
    assert "Exotic Ideas" not in result


# --- structured exotic_recommendations --------------------------------------

def test_exotic_recommendation_model_shape():
    from services.stake.analysis.models import ExoticRecommendation

    rec = ExoticRecommendation(
        market="trifecta_box", selections=[3, 5, 7],
        confidence=0.55, rationale="Tight top-3 cluster.",
    )
    assert rec.market == "trifecta_box"
    assert rec.selections == [3, 5, 7]


def test_exotic_recommendation_rejects_unknown_market():
    from services.stake.analysis.models import ExoticRecommendation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExoticRecommendation(
            market="quint_bogus", selections=[3], confidence=0.5, rationale="x",
        )


def test_exotic_recommendation_rejects_empty_selections():
    from services.stake.analysis.models import ExoticRecommendation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExoticRecommendation(
            market="exacta", selections=[], confidence=0.5, rationale="x",
        )


def test_no_bets_card_renders_structured_exotic_recommendations():
    state = {
        "skip_signal": False,
        "final_bets": [],
        "enriched_runners": [],
        "analysis_result": {
            "exotic_recommendations": [
                {
                    "market": "trifecta_box",
                    "selections": [3, 5, 7],
                    "confidence": 0.55,
                    "rationale": "Top-3 AI probs cluster tightly.",
                },
                {
                    "market": "exacta",
                    "selections": [3, 5],
                    "confidence": 0.40,
                    "rationale": "Favourite dominant.",
                },
            ],
        },
    }
    result = format_recommendation(state)
    assert "Exotic Ideas" in result
    assert "TRIFECTA BOX" in result
    assert "3-5-7" in result
    assert "conf 55%" in result
    assert "EXACTA" in result
    assert "3-5" in result
    assert "conf 40%" in result
    assert "Top-3 AI probs cluster" in result


def test_structured_exotic_preferred_over_free_suggestions():
    """If both structured + free-string fields are populated, structured wins
    (no duplicate section)."""
    state = {
        "skip_signal": False,
        "final_bets": [],
        "enriched_runners": [],
        "analysis_result": {
            "exotic_recommendations": [{
                "market": "qps", "selections": [3],
                "confidence": 0.6, "rationale": "Safe place cover.",
            }],
            "exotic_suggestions": ["legacy free string — should NOT appear"],
        },
    }
    result = format_recommendation(state)
    assert "QPS" in result
    assert "legacy free string" not in result


def test_structured_exotic_escapes_html():
    state = {
        "skip_signal": False,
        "final_bets": [],
        "enriched_runners": [],
        "analysis_result": {
            "exotic_recommendations": [{
                "market": "exacta", "selections": [3, 5],
                "confidence": 0.5, "rationale": "<script>bad</script>",
            }],
        },
    }
    result = format_recommendation(state)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_regular_card_renders_structured_exotic():
    state = {
        "skip_signal": False,
        "final_bets": [{
            "runner_name": "Pick", "runner_number": 3,
            "label": "highest_win_probability",
            "bet_type": "win", "ev": 0.1, "kelly_pct": 2.0,
            "usdt_amount": 1.5, "reasoning": "ok", "data_sparse": False,
        }],
        "analysis_result": {
            "exotic_recommendations": [{
                "market": "trifecta", "selections": [3, 5, 7],
                "confidence": 0.4, "rationale": "Order play.",
            }],
        },
    }
    result = format_recommendation(state)
    assert "TRIFECTA" in result
    assert "3-5-7" in result


# --- formatter: exotics in regular bet card ---------------------------------

def test_regular_recommendation_card_includes_exotics():
    state = {
        "skip_signal": False,
        "final_bets": [
            {
                "runner_name": "Main Pick", "runner_number": 3,
                "label": "highest_win_probability",
                "bet_type": "win", "ev": 0.12, "kelly_pct": 3.0,
                "usdt_amount": 2.0, "reasoning": "strong form",
                "data_sparse": False,
            },
        ],
        "analysis_result": {
            "exotic_suggestions": ["Exacta 3>7: clean cover."],
        },
    }
    result = format_recommendation(state)
    assert "Bet Recommendations" in result
    assert "Exotic Ideas" in result
    assert "Exacta 3" in result


# --- keyboards ---------------------------------------------------------------

def test_report_result_kb_has_two_buttons():
    kb = report_result_kb()
    # InlineKeyboardMarkup exposes inline_keyboard: list[list[InlineKeyboardButton]]
    flat = [btn for row in kb.inline_keyboard for btn in row]
    assert len(flat) == 2
    callbacks = {btn.callback_data for btn in flat}
    # TrackingCB packs action into the callback_data string; both must be present
    assert any("report_only" in cd for cd in callbacks)
    assert any("skip_result" in cd for cd in callbacks)


# --- callback routing --------------------------------------------------------

@pytest.mark.asyncio
async def test_report_only_callback_transitions_to_awaiting_result():
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.answer = AsyncMock()

    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    data = TrackingCB(action="report_only")
    await handle_tracking_choice(cb, data, state)

    state.update_data.assert_awaited_once_with(is_placed=False)
    state.set_state.assert_awaited_once_with(PipelineStates.awaiting_result)
    cb.message.answer.assert_awaited_once()
    body = cb.message.answer.await_args.args[0]
    assert "TRACKED" in body
    assert "no bet" in body.lower()


@pytest.mark.asyncio
async def test_skip_result_callback_returns_to_idle():
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.answer = AsyncMock()

    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    data = TrackingCB(action="skip_result")
    await handle_tracking_choice(cb, data, state)

    # skip_result takes the early-return path: no update_data, state=idle
    state.update_data.assert_not_awaited()
    state.set_state.assert_awaited_once_with(PipelineStates.idle)
    cb.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_placed_callback_still_works_unchanged():
    """Regression: existing Placed flow must not be affected by the new
    report_only / skip_result branches."""
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.answer = AsyncMock()

    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    data = TrackingCB(action="placed")
    await handle_tracking_choice(cb, data, state)

    state.update_data.assert_awaited_once_with(is_placed=True)
    state.set_state.assert_awaited_once_with(PipelineStates.awaiting_result)


@pytest.mark.asyncio
async def test_tracked_callback_still_works_unchanged():
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.answer = AsyncMock()

    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()

    data = TrackingCB(action="tracked")
    await handle_tracking_choice(cb, data, state)

    state.update_data.assert_awaited_once_with(is_placed=False)
    state.set_state.assert_awaited_once_with(PipelineStates.awaiting_result)
