"""
LangGraph pipeline node functions for the Stake Advisor parse pipeline.

Each node function takes a PipelineState and returns a partial update dict.
LangGraph merges the update into the running state automatically.

Nodes:
    parse_node                  — LLM extraction + ambiguity detection (PIPELINE-02)
    calc_node                   — Odds math: decimal conversion, implied probability, overround
    pre_skip_check_node         — Tier 1 skip: bookmaker margin threshold check (D-06)
    analysis_node               — LLM qualitative analysis with pre-computed EV values (ARCH-01)
    sizing_node                 — Deterministic Kelly sizing with portfolio caps (BET-01..BET-07)
    format_recommendation_node  — HTML Telegram card formatter (D-13)
"""

import html
import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger("stake")

from services.stake.analysis.models import AnalysisResult
from services.stake.analysis.prompts import ANALYSIS_SYSTEM_PROMPT
from services.stake.bankroll import repository as _bankroll_repo_module
# NOTE: `BankrollRepository` is looked up through the `services.stake.pipeline.nodes`
# package attribute at call time (see `_bankroll_repo_cls()` below) so that
# tests which do `@patch("services.stake.pipeline.nodes.BankrollRepository")`
# still hit the sizing_node / drawdown_check_node code paths even though those
# functions now live in this submodule.
from services.stake.parser.llm_parser import StakeParser
from services.stake.parser.math import (
    apply_portfolio_caps,
    apply_sparsity_discount,
    bet_size_usdt,
    expected_value,
    implied_probability,
    kelly_fraction,
    no_vig_probability,
    odds_drift_pct,
    overround,
    place_bet_ev,
    recalculate_without_scratches,
    to_decimal,
)
from services.stake.pipeline.formatter import format_recommendation
from services.stake.pipeline.state import PipelineState
from services.stake.settings import get_stake_settings


def _bankroll_repo_cls():
    """Resolve `BankrollRepository` through the package namespace so tests
    that patch `services.stake.pipeline.nodes.BankrollRepository` work.

    Falls back to the real class from the bankroll submodule if the package
    attribute hasn't been populated yet (e.g. during early import).
    """
    import services.stake.pipeline.nodes as _pkg
    return getattr(
        _pkg, "BankrollRepository", _bankroll_repo_module.BankrollRepository,
    )


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

    # Reject if no runners extracted (input was not race data)
    if not result.runners:
        return {"error": "No race data found in input. Please paste Stake.com race text with runners and odds."}

    # Reject if no runner has odds (LLM may have hallucinated runner names from garbage)
    runners_with_odds = [r for r in result.runners if r.win_odds is not None and r.status == "active"]
    if not runners_with_odds:
        return {"error": "No runners with odds found. Please paste race data that includes odds for each runner."}

    # PIPELINE-02: detect ambiguous/incomplete fields
    ambiguous: list[str] = []

    # Check runner count mismatch (account for scratched runners)
    if (
        result.runner_count is not None
        and len(result.runners) > 0
    ):
        active_count = sum(1 for r in result.runners if r.status == "active")
        total_count = len(result.runners)
        # Mismatch if neither active nor total count matches the stated runner_count
        if result.runner_count != total_count and result.runner_count != active_count:
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
        # Filter out false bankroll detections: amounts under $1 are odds/bet amounts
        "detected_bankroll": result.detected_bankroll if result.detected_bankroll and result.detected_bankroll >= 1.0 else None,
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


def drawdown_check_node(state: PipelineState) -> dict[str, Any]:
    """RISK-01: Short-circuit if bankroll has dropped >=threshold% from peak.

    Per D-09: fires before analysis to save API cost.
    Per D-10: threshold configurable via settings.risk.drawdown_threshold_pct.

    Returns skip_signal=True with a drawdown reason when the circuit breaker
    trips. Returns {} when data is unavailable or drawdown is unlocked.

    Args:
        state: PipelineState (no specific fields required).

    Returns:
        Partial state update:
        - {"skip_signal": True, "skip_reason": str, "skip_tier": 0} on trip
        - {} when check passes or cannot be computed
    """
    settings = get_stake_settings()
    repo = _bankroll_repo_cls()(db_path=settings.database_path)

    peak = repo.get_peak_balance()
    current = repo.get_balance()

    if peak is None or current is None or peak <= 0:
        return {}  # No data — cannot check

    if repo.is_drawdown_unlocked():
        return {}  # User explicitly unlocked

    threshold = settings.risk.drawdown_threshold_pct
    drawdown_pct = ((peak - current) / peak) * 100.0

    if drawdown_pct >= threshold:
        return {
            "skip_signal": True,
            "skip_reason": (
                f"DRAWDOWN PROTECTION: balance {current:.2f} USDT is "
                f"{drawdown_pct:.1f}% below peak {peak:.2f} USDT. "
                f"Use /unlock_drawdown to override."
            ),
            "skip_tier": 0,
        }
    return {}


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
    # If skip_signal is explicitly False, user chose to continue past margin check
    if state.get("skip_signal") is False:
        logger.info("[SKIP-CHECK] User forced continue — bypassing margin check")
        return {}

    overround_active = state.get("overround_active")
    if overround_active is None:
        return {}

    settings = get_stake_settings()
    threshold = settings.sizing.skip_overround_threshold
    margin_pct = (overround_active - 1.0) * 100.0

    logger.info("[SKIP-CHECK] Margin %.1f%% vs threshold %.1f%%", margin_pct, threshold)

    if margin_pct > threshold:
        logger.info("[SKIP-CHECK] SKIP — margin too high")
        return {
            "skip_signal": True,
            "skip_reason": (
                f"Bookmaker margin {margin_pct:.1f}% exceeds threshold {threshold:.1f}% "
                f"— race not worth analysing (overround {overround_active:.4f})"
            ),
            "skip_tier": 1,
        }

    return {"skip_signal": False}


# ---------------------------------------------------------------------------
# Phase 2 Analysis nodes — Plan 02-04
# ---------------------------------------------------------------------------


def _build_lessons_block(db_path: str) -> str:
    """Query stake_lessons for top-5 rules and last-3 failure modes.
    Per REFLECT-03/D-08: injected into analysis prompt for next race."""
    from services.stake.reflection.repository import LessonsRepository
    repo = LessonsRepository(db_path)
    top_rules = repo.get_top_rules(limit=5)
    failure_modes = repo.get_recent_failures(limit=3)

    if not top_rules and not failure_modes:
        return ""

    # Increment application count for rules being injected
    rule_ids = [r.get("id") for r in top_rules if r.get("id")]
    failure_ids = [f.get("id") for f in failure_modes if f.get("id")]
    all_ids = [i for i in rule_ids + failure_ids if i is not None]
    if all_ids:
        repo.increment_application_count(all_ids)

    lines = ["\n=== LEARNED LESSONS (from previous bets) ==="]
    if top_rules:
        lines.append("Rules (most applied):")
        for rule in top_rules:
            lines.append(f"  [{rule['error_tag']}] {rule['rule_sentence']}")
    if failure_modes:
        lines.append("Recent failure modes (avoid these):")
        for fail in failure_modes:
            lines.append(f"  [{fail['error_tag']}] {fail['rule_sentence']}")
    lines.append("=== END LESSONS ===\n")
    return "\n".join(lines)


def _build_analysis_prompt(state: PipelineState, research_results: dict, no_vig_data: list[dict]) -> str:
    """Build analysis prompt for the LLM with pre-computed mathematical values.

    Includes race context, per-runner no-vig probabilities (as mathematical baseline),
    and research summaries. Per ARCH-01: LLM gets pre-computed math, not raw odds.

    Args:
        state: PipelineState with enriched_runners populated.
        research_results: ResearchOutput.model_dump() dict.
        no_vig_data: List of dicts with runner_number, runner_name, no_vig_prob, decimal_odds.

    Returns:
        Formatted prompt string.
    """
    parsed_race = state.get("parsed_race")
    enriched_runners = state.get("enriched_runners") or []
    overround_active = state.get("overround_active")

    lines: list[str] = []

    # Race header
    lines.append("=== RACE INFORMATION ===")
    if parsed_race:
        race_dict = parsed_race if isinstance(parsed_race, dict) else (
            parsed_race.model_dump() if hasattr(parsed_race, "model_dump") else {}
        )
        track = race_dict.get("track") or (parsed_race.track if hasattr(parsed_race, "track") else None)
        race_number = race_dict.get("race_number") or (parsed_race.race_number if hasattr(parsed_race, "race_number") else None)
        race_name = race_dict.get("race_name") or (parsed_race.race_name if hasattr(parsed_race, "race_name") else None)
        distance = race_dict.get("distance") or (parsed_race.distance if hasattr(parsed_race, "distance") else None)
        surface = race_dict.get("surface") or (parsed_race.surface if hasattr(parsed_race, "surface") else None)
        place_terms = race_dict.get("place_terms") or (parsed_race.place_terms if hasattr(parsed_race, "place_terms") else None)

        if track:
            lines.append(f"Track: {track}")
        if race_number:
            lines.append(f"Race: #{race_number}")
        if race_name:
            lines.append(f"Name: {race_name}")
        if distance:
            lines.append(f"Distance: {distance}")
        if surface:
            lines.append(f"Surface: {surface}")
        if place_terms:
            lines.append(f"Place terms: {place_terms}")

    if overround_active is not None:
        margin_pct = (overround_active - 1.0) * 100.0
        lines.append(f"Bookmaker margin: {margin_pct:.1f}% (overround {overround_active:.4f})")

    lines.append("")
    lines.append("=== RUNNERS WITH PRE-COMPUTED MATH ===")
    lines.append(
        "These no-vig probabilities are your mathematical baseline. "
        "Assign your ai_win_prob for each runner based on research + math. "
        "Do NOT generate USDT amounts."
    )
    lines.append("")

    # Map research by runner name for easy lookup
    research_by_name: dict[str, dict] = {}
    if research_results and research_results.get("runners"):
        for r in research_results["runners"]:
            research_by_name[r.get("runner_name", "").lower()] = r

    for nv in no_vig_data:
        runner_num = nv["runner_number"]
        runner_name = nv["runner_name"]
        no_vig_prob = nv["no_vig_prob"]
        decimal_odds = nv["decimal_odds"]

        # EV at market probability (what the book says)
        market_implied = nv.get("implied_prob", 0)
        ev_market = expected_value(market_implied, decimal_odds) if market_implied else None

        parts = [
            f"#{runner_num} {runner_name}",
            f"Decimal odds: {decimal_odds:.2f}",
            f"No-vig prob: {no_vig_prob:.1%}",
        ]
        if ev_market is not None:
            parts.append(f"Market EV at no-vig: {ev_market:+.4f}")

        # Look up odds drift
        runner_enriched = next(
            (r for r in enriched_runners if r.get("number") == runner_num), None
        )
        if runner_enriched and runner_enriched.get("odds_drift") is not None:
            parts.append(f"Odds drift: {runner_enriched['odds_drift']:+.1f}%")
        if runner_enriched and runner_enriched.get("form_string"):
            parts.append(f"Form: {runner_enriched['form_string']}")
        if runner_enriched and runner_enriched.get("jockey"):
            parts.append(f"J: {runner_enriched['jockey']}")
        if runner_enriched and runner_enriched.get("trainer"):
            parts.append(f"T: {runner_enriched['trainer']}")

        lines.append(" | ".join(parts))

        # Research data for this runner
        research = research_by_name.get(runner_name.lower())
        if research:
            data_quality = research.get("data_quality", "none")
            lines.append(f"  Research quality: {data_quality}")
            if research.get("form_summary"):
                lines.append(f"  Form: {research['form_summary']}")
            if research.get("trainer_stats"):
                lines.append(f"  Trainer: {research['trainer_stats']}")
            if research.get("expert_opinion"):
                lines.append(f"  Expert: {research['expert_opinion']}")
            if research.get("external_odds"):
                lines.append(f"  External odds: {research['external_odds']}")
            if research.get("confidence_notes"):
                lines.append(f"  Confidence: {research['confidence_notes']}")

        lines.append("")

    # Overall research notes
    if research_results and research_results.get("overall_notes"):
        lines.append("=== OVERALL RACE CONTEXT ===")
        lines.append(research_results["overall_notes"])
        lines.append("")

    lines.append("=== YOUR TASK ===")
    lines.append(
        "For each runner, assign a label (highest_win_probability / best_value / "
        "best_place_candidate / no_bet) and ai_win_prob (0.0–1.0). "
        "Optionally assign ai_place_prob for place candidates. "
        "Provide 2-3 sentences of reasoning per runner. "
        "If the race should be skipped overall, set overall_skip=True with skip_reason. "
        "If you override despite +EV, set ai_override=True with override_reason. "
        "Note any market discrepancies in market_discrepancy_notes."
    )

    return "\n".join(lines)


async def analysis_node(state: PipelineState) -> dict[str, Any]:
    """Run LLM qualitative analysis with pre-computed EV values.

    Per ARCH-01: LLM receives pre-computed no-vig probabilities as mathematical
    baseline. LLM assigns ai_win_prob for each runner based on research + math.
    LLM does NOT generate USDT amounts.

    Args:
        state: PipelineState with enriched_runners, research_results, overround_active.

    Returns:
        {"analysis_result": AnalysisResult.model_dump()} on success.
        {} if skip_signal is True (already skipped).
        {"error": str} on research failure or LLM exception.
    """
    if state.get("skip_signal"):
        return {}

    research_error = state.get("research_error")
    if research_error is not None:
        logger.error("[ANALYSIS] Research failed: %s", research_error)
        return {"error": f"Research failed: {research_error}"}

    try:
        t0 = time.time()
        settings = get_stake_settings()
        enriched_runners = state.get("enriched_runners") or []
        logger.info("[ANALYSIS] Starting analysis — model=%s, runners=%d",
                     settings.analysis.model, len(enriched_runners))
        overround_active = state.get("overround_active")
        research_results = state.get("research_results") or {}

        # Compute no-vig probabilities for active runners as mathematical baseline
        no_vig_data: list[dict] = []
        for runner in enriched_runners:
            if runner.get("status") == "scratched":
                continue
            implied_prob = runner.get("implied_prob")
            decimal_odds = runner.get("decimal_odds")
            if implied_prob is None or decimal_odds is None:
                continue

            nvp = (
                no_vig_probability(implied_prob, overround_active)
                if overround_active
                else implied_prob
            )
            no_vig_data.append({
                "runner_number": runner.get("number"),
                "runner_name": runner.get("name", "Unknown"),
                "no_vig_prob": nvp,
                "decimal_odds": decimal_odds,
                "implied_prob": implied_prob,
            })

        prompt = _build_analysis_prompt(state, research_results, no_vig_data)

        # REFLECT-03/D-08: Prepend learned lessons to analysis prompt
        lessons_block = _build_lessons_block(settings.database_path)
        if lessons_block:
            prompt = lessons_block + prompt

        llm = ChatOpenAI(
            openai_api_base="https://openrouter.ai/api/v1",
            openai_api_key=settings.openrouter_api_key,
            model=settings.analysis.model,
            temperature=settings.analysis.temperature,
            max_tokens=settings.analysis.max_tokens,
        ).with_structured_output(AnalysisResult)

        result: AnalysisResult = await llm.ainvoke([
            SystemMessage(content=ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])

        analysis_dict = result.model_dump()
        labels = [r.get("label", "?") for r in analysis_dict.get("recommendations", [])]
        logger.info("[ANALYSIS] Done in %.1fs — labels: %s, skip=%s",
                     time.time() - t0, labels, analysis_dict.get("overall_skip"))
        return {"analysis_result": analysis_dict}

    except Exception as e:
        logger.exception("[ANALYSIS] Failed: %s", e)
        return {"error": f"Analysis failed: {str(e)}"}


def sizing_node(state: PipelineState) -> dict[str, Any]:
    """Deterministic Kelly sizing with portfolio cap enforcement.

    Per ARCH-01: ALL numerical calculations are pure Python — never LLM.
    Enforces quarter-Kelly, 3% per-bet cap, 5% total exposure, 2 win bet max.

    Args:
        state: PipelineState with analysis_result and enriched_runners populated.

    Returns:
        {"final_bets": list[dict]} on success.
        {} if skip_signal is True.
        {"skip_signal": True, "skip_reason": str, "skip_tier": 2, "final_bets": []}
            if analysis recommends skipping.
    """
    if state.get("skip_signal"):
        return {}

    analysis_result = state.get("analysis_result")
    if not analysis_result:
        logger.warning("[SIZING] No analysis_result — returning empty bets")
        return {"final_bets": []}

    # Check Tier 2 skip: AI recommends skipping
    if analysis_result.get("overall_skip") or analysis_result.get("ai_override"):
        logger.info("[SIZING] Tier 2 skip — AI recommends skipping")
        skip_reason = (
            analysis_result.get("skip_reason")
            or analysis_result.get("override_reason")
            or "AI recommends skipping this race"
        )
        return {
            "skip_signal": True,
            "skip_reason": skip_reason,
            "skip_tier": 2,
            "final_bets": [],
        }

    settings = get_stake_settings()
    repo = _bankroll_repo_cls()(settings.database_path)
    bankroll = repo.get_balance()

    if bankroll is None or bankroll <= 0:
        return {"final_bets": []}

    sizing = settings.sizing
    enriched_runners = state.get("enriched_runners") or []

    # Build lookup: runner_number -> enriched runner dict
    runner_by_number: dict[int, dict] = {
        r["number"]: r for r in enriched_runners if r.get("number") is not None
    }

    # Build lookup: runner_name (lower) -> enriched runner dict
    runner_by_name: dict[str, dict] = {
        r["name"].lower(): r
        for r in enriched_runners
        if r.get("name")
    }

    # Build research sparse lookup: runner_name (lower) -> bool
    research_results = state.get("research_results") or {}
    sparse_by_name: dict[str, bool] = {}
    if research_results.get("runners"):
        for r in research_results["runners"]:
            name_key = r.get("runner_name", "").lower()
            sparse_by_name[name_key] = r.get("data_quality") in ("sparse", "none")

    # Helper to look up place_odds for a runner
    parsed_race = state.get("parsed_race")
    parsed_runners_list = []
    if parsed_race is not None:
        parsed_runners_list = (
            parsed_race.runners
            if hasattr(parsed_race, "runners")
            else parsed_race.get("runners", []) if isinstance(parsed_race, dict)
            else []
        )

    def _get_place_odds(runner_num: int) -> float | None:
        for pr in parsed_runners_list:
            pr_num = getattr(pr, "number", None) or (pr.get("number") if isinstance(pr, dict) else None)
            if pr_num == runner_num:
                return getattr(pr, "place_odds", None) or (pr.get("place_odds") if isinstance(pr, dict) else None)
        return None

    raw_bets: list[dict] = []

    for rec in analysis_result.get("recommendations", []):
        label = rec.get("label", "no_bet")
        if label == "no_bet":
            continue

        runner_number = rec.get("runner_number")
        runner_name = rec.get("runner_name", "")
        ai_win_prob = rec.get("ai_win_prob", 0.0)
        ai_place_prob = rec.get("ai_place_prob") or ai_win_prob * 1.5

        # Look up runner data by number first, then by name
        runner_data = runner_by_number.get(runner_number)
        if runner_data is None:
            runner_data = runner_by_name.get(runner_name.lower())
        if runner_data is None:
            continue

        decimal_odds = runner_data.get("decimal_odds")
        if decimal_odds is None:
            continue

        # Check sparsity early
        is_sparse = sparse_by_name.get(runner_name.lower(), False)

        # ── Win bet ──
        if label in ("highest_win_probability", "best_value"):
            ev_val = expected_value(ai_win_prob, decimal_odds)
            if ev_val > 0:
                kf = kelly_fraction(ai_win_prob, decimal_odds)
                amount = bet_size_usdt(
                    bankroll, kf,
                    sizing.kelly_multiplier,
                    sizing.per_bet_cap_pct,
                    sizing.min_bet_usdt,
                )
                if is_sparse:
                    amount = apply_sparsity_discount(amount, True, sizing.sparsity_discount)
                if amount > 0:
                    raw_bets.append({
                        "runner_name": runner_name,
                        "runner_number": runner_number,
                        "label": label,
                        "bet_type": "win",
                        "type": "win",
                        "ev": ev_val,
                        "kelly_pct": round(kf * 100, 2),
                        "amount": amount,
                        "usdt_amount": amount,
                        "decimal_odds": decimal_odds,
                        "place_odds": None,
                        "data_sparse": is_sparse,
                        "reasoning": rec.get("reasoning", ""),
                    })

        # ── Place bet (for ALL non-no_bet runners with place_odds) ──
        place_odds_val = _get_place_odds(runner_number)
        if place_odds_val is not None and ai_place_prob > 0:
            p_ev = place_bet_ev(ai_place_prob, place_odds_val)
            if p_ev > 0:
                kf = kelly_fraction(ai_place_prob, place_odds_val)
                amount = bet_size_usdt(
                    bankroll, kf,
                    sizing.kelly_multiplier,
                    sizing.per_bet_cap_pct,
                    sizing.min_bet_usdt,
                )
                if is_sparse:
                    amount = apply_sparsity_discount(amount, True, sizing.sparsity_discount)
                if amount > 0:
                    raw_bets.append({
                        "runner_name": runner_name,
                        "runner_number": runner_number,
                        "label": label,
                        "bet_type": "place",
                        "type": "place",
                        "ev": p_ev,
                        "kelly_pct": round(kf * 100, 2),
                        "amount": amount,
                        "usdt_amount": amount,
                        "decimal_odds": decimal_odds,
                        "place_odds": place_odds_val,
                        "data_sparse": is_sparse,
                        "reasoning": rec.get("reasoning", ""),
                    })

    # Sort by EV descending before portfolio caps
    raw_bets.sort(key=lambda b: b["ev"], reverse=True)

    # Apply portfolio caps (max win bets, total exposure)
    capped_bets = apply_portfolio_caps(
        raw_bets,
        bankroll,
        sizing.max_total_exposure_pct,
        sizing.max_win_bets,
    )

    # Normalise output: ensure both "usdt_amount" and "amount" keys present
    final_bets = []
    for b in capped_bets:
        bet = dict(b)
        bet["usdt_amount"] = bet.get("usdt_amount") or bet.get("amount", 0.0)
        final_bets.append(bet)

    total_usdt = sum(b.get("usdt_amount", 0) for b in final_bets)
    logger.info("[SIZING] %d raw bets → %d after caps | total %.2f USDT / %.2f bankroll (%.1f%%)",
                len(raw_bets), len(final_bets), total_usdt, bankroll,
                (total_usdt / bankroll * 100) if bankroll else 0)
    for b in final_bets:
        logger.info("[SIZING]   #%s %s | %s %.2f USDT | EV %+.3f | Kelly %.1f%%",
                    b.get("runner_number"), b.get("runner_name"),
                    b.get("bet_type"), b.get("usdt_amount", 0),
                    b.get("ev", 0), b.get("kelly_pct", 0))

    return {"final_bets": final_bets}


def format_recommendation_node(state: PipelineState) -> dict[str, Any]:
    """Format final bet recommendations as Telegram HTML cards.

    Per D-13: runner cards show name, label, EV, Kelly%, USDT, reasoning.
    Per CLAUDE.md: ALL variable strings are escaped with html.escape() to
    prevent Telegram parse_mode=HTML failures.

    Args:
        state: PipelineState with final_bets, analysis_result, skip_signal populated.

    Returns:
        {"recommendation_text": str} — always set.
    """
    # Handle error state — show error message instead of recommendations
    error = state.get("error")
    if error:
        text = f"<b>Analysis Error</b>\n\n{html.escape(str(error))}"
        return {"recommendation_text": text}

    text = format_recommendation(dict(state))
    return {"recommendation_text": text}
