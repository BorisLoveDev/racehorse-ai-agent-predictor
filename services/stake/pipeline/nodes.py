"""
LangGraph pipeline node functions for the Stake Advisor parse pipeline.

Each node function takes a PipelineState and returns a partial update dict.
LangGraph merges the update into the running state automatically.

Nodes:
    parse_node  — LLM extraction + ambiguity detection (PIPELINE-02)
    calc_node   — Odds math: decimal conversion, implied probability, overround
"""

from typing import Any

from services.stake.parser.llm_parser import StakeParser
from services.stake.parser.math import (
    to_decimal,
    implied_probability,
    overround,
    recalculate_without_scratches,
    odds_drift_pct,
)
from services.stake.pipeline.state import PipelineState
from services.stake.settings import get_stake_settings


async def parse_node(state: PipelineState) -> dict[str, Any]:
    """Run LLM extraction on raw_input and detect ambiguous fields.

    Per PIPELINE-02: populates ambiguous_fields list when:
    - runner_count in paste doesn't match extracted runner count
    - more than 30% of runners are missing win_odds
    - track field is None (venue unknown)

    Args:
        state: PipelineState with raw_input populated.

    Returns:
        Partial update with parsed_race, detected_bankroll, ambiguous_fields.
        On error, returns {"error": str(e)}.
    """
    raw_text = state.get("raw_input", "")
    if not raw_text:
        return {"error": "No input text to parse"}

    try:
        parser = StakeParser()
        result = await parser.parse(raw_text)
    except Exception as e:
        return {"error": str(e)}

    # PIPELINE-02: detect ambiguous/incomplete fields
    ambiguous: list[str] = []

    # Check runner count mismatch
    if (
        result.runner_count is not None
        and len(result.runners) > 0
        and result.runner_count != len(result.runners)
    ):
        ambiguous.append("runner_count_mismatch")

    # Check missing odds threshold (>30% of runners missing win_odds)
    if result.runners:
        missing_odds_count = sum(
            1 for r in result.runners if r.win_odds is None and r.status == "active"
        )
        active_count = sum(1 for r in result.runners if r.status == "active")
        if active_count > 0 and missing_odds_count / active_count > 0.30:
            ambiguous.append("missing_odds")

    # Check for unknown track
    if result.track is None:
        ambiguous.append("track")

    return {
        "parsed_race": result,
        "detected_bankroll": result.detected_bankroll,
        "ambiguous_fields": ambiguous if ambiguous else [],
    }


def calc_node(state: PipelineState) -> dict[str, Any]:
    """Calculate odds math for all runners.

    Converts odds to decimal, calculates implied probability, odds drift,
    and computes overround for raw (all runners) and active (non-scratched).

    Per ARCH-01: all numerical calculations are deterministic Python — never LLM.

    Args:
        state: PipelineState with parsed_race populated.

    Returns:
        Partial update with enriched_runners, overround_raw, overround_active.
    """
    parsed_race = state.get("parsed_race")
    if not parsed_race:
        return {"enriched_runners": [], "overround_raw": None, "overround_active": None}

    enriched: list[dict] = []

    for runner in parsed_race.runners:
        entry: dict[str, Any] = {
            "number": runner.number,
            "name": runner.name,
            "status": runner.status,
            "barrier": runner.barrier,
            "weight": runner.weight,
            "jockey": runner.jockey,
            "trainer": runner.trainer,
            "form_string": runner.form_string,
            "tags": runner.tags,
            "running_style": runner.running_style,
            "market_rank": runner.market_rank,
            "tips_text": runner.tips_text,
            "decimal_odds": None,
            "implied_prob": None,
            "odds_drift": None,
        }

        # Convert win_odds to decimal and calculate implied probability
        if runner.win_odds is not None and runner.win_odds_format is not None:
            try:
                decimal = to_decimal(runner.win_odds_format, runner.win_odds)
                entry["decimal_odds"] = decimal
                entry["implied_prob"] = implied_probability(decimal)
            except (ValueError, ZeroDivisionError):
                pass

        # Calculate odds drift from opening to current
        if runner.opening_odds is not None and entry["decimal_odds"] is not None:
            try:
                opening_decimal = to_decimal(
                    runner.win_odds_format or "decimal", runner.opening_odds
                )
                entry["odds_drift"] = odds_drift_pct(opening_decimal, entry["decimal_odds"])
            except (ValueError, ZeroDivisionError):
                pass

        enriched.append(entry)

    # Calculate overround_raw: all runners with decimal_odds
    all_odds = [e["decimal_odds"] for e in enriched if e["decimal_odds"] is not None]
    overround_raw: float | None = None
    if all_odds:
        try:
            overround_raw = overround(all_odds)
        except ValueError:
            pass

    # Calculate overround_active: active runners only via recalculate_without_scratches
    overround_active: float | None = None
    try:
        overround_active = recalculate_without_scratches(parsed_race.runners)
    except ValueError:
        pass

    return {
        "enriched_runners": enriched,
        "overround_raw": overround_raw,
        "overround_active": overround_active,
    }


def pre_skip_check_node(state: PipelineState) -> dict[str, Any]:
    """Pre-analysis skip check based on bookmaker overround margin.

    Implements D-06: if the bookmaker margin is too high, the race is
    flagged to skip before expensive LLM research/analysis steps run.
    This saves API costs on races where the book is heavily squeezed.

    Tier 1 skip: overround margin > skip_overround_threshold (default 15%).

    Args:
        state: PipelineState with overround_active populated by calc_node.

    Returns:
        Partial state update dict:
        - {"skip_signal": True, "skip_reason": str, "skip_tier": 1} if skip triggered
        - {"skip_signal": False} if overround is within acceptable range
        - {} if overround_active is not available (no decision made)
    """
    overround_active = state.get("overround_active")
    if overround_active is None:
        return {}

    settings = get_stake_settings()
    threshold = settings.sizing.skip_overround_threshold
    margin_pct = (overround_active - 1.0) * 100.0

    if margin_pct > threshold:
        return {
            "skip_signal": True,
            "skip_reason": (
                f"Bookmaker margin {margin_pct:.1f}% exceeds threshold {threshold:.1f}% "
                f"— race not worth analysing (overround {overround_active:.4f})"
            ),
            "skip_tier": 1,
        }

    return {"skip_signal": False}
