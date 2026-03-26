"""
Race summary formatter for Telegram display.

Formats parsed and enriched pipeline state as HTML for aiogram messages.
Per D-17, D-18, D-21: shows track, race number, distance, surface, place terms,
runners with odds/probability/drift, overround margin, and ambiguous data warnings.

Also provides format_recommendation() for Phase 2 bet recommendation cards.
Per D-13, D-15: runner cards with name, label, EV, Kelly%, USDT, reasoning.
ALL variable strings are escaped with html.escape() per CLAUDE.md Common Pitfalls.

Exported:
    format_race_summary(state: dict) -> str
    format_recommendation(state: dict) -> str
"""

import html


def _get(obj, key, default=None):
    """Get attribute from Pydantic model or dict transparently."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def format_race_summary(state: dict) -> str:
    """Format parsed race as HTML for Telegram message.

    Works with both Pydantic ParsedRace objects and serialized dicts
    (after Redis FSM round-trip).
    """
    race = state.get("parsed_race")
    if not race:
        return "No race data parsed."

    lines: list[str] = []

    # Race header: track | Race N | name
    header_parts = []
    if _get(race, "track"):
        header_parts.append(f"<b>{_get(race, 'track')}</b>")
    if _get(race, "race_number"):
        header_parts.append(f"Race {_get(race, 'race_number')}")
    if _get(race, "race_name"):
        header_parts.append(_get(race, "race_name"))
    lines.append(" | ".join(header_parts) if header_parts else "<b>Race Summary</b>")

    # Race details line
    details = []
    if _get(race, "distance"):
        details.append(f"Distance: {_get(race, 'distance')}")
    if _get(race, "surface"):
        details.append(f"Surface: {_get(race, 'surface')}")
    if _get(race, "place_terms"):
        details.append(f"Place: {_get(race, 'place_terms')}")
    if _get(race, "date"):
        details.append(f"Date: {_get(race, 'date')}")
    if _get(race, "time_to_start"):
        details.append(f"Starts in: {_get(race, 'time_to_start')}")
    if details:
        lines.append("  ".join(details))

    # Overround section
    ovr_raw = state.get("overround_raw")
    ovr_active = state.get("overround_active")
    if ovr_raw is not None:
        margin = (ovr_raw - 1) * 100
        lines.append(f"\nOverround: {ovr_raw:.2f} (margin {margin:.1f}%)")
    if ovr_active is not None and ovr_active != ovr_raw:
        margin_a = (ovr_active - 1) * 100
        lines.append(f"Active only: {ovr_active:.2f} (margin {margin_a:.1f}%)")

    # Runners table
    lines.append("\n<b>Runners:</b>")
    enriched = state.get("enriched_runners", [])
    for r in enriched:
        status = r.get("status", "active")
        odds_str = f"{r['decimal_odds']:.2f}" if r.get("decimal_odds") is not None else "—"
        prob_str = f"{r['implied_prob'] * 100:.1f}%" if r.get("implied_prob") is not None else "—"
        tags_str = f" [{', '.join(r['tags'])}]" if r.get("tags") else ""
        drift_str = ""
        if r.get("odds_drift") is not None:
            drift_str = f" ({r['odds_drift']:+.1f}%)"

        if status == "scratched":
            lines.append(f"  <s>{r['number']}. {r['name']}</s> SCRATCHED")
        else:
            lines.append(
                f"  {r['number']}. {r['name']} — {odds_str} ({prob_str}){drift_str}{tags_str}"
            )

    # Bet types available
    bet_types = _get(race, "bet_types_available")
    if bet_types:
        lines.append(f"\nBet types: {', '.join(bet_types)}")

    # PIPELINE-02: ambiguous fields warning
    ambiguous = state.get("ambiguous_fields") or []
    if ambiguous:
        # Show user-friendly field names
        display_names = {
            "runner_count_mismatch": "runner count",
            "missing_odds": "missing odds",
            "track": "track/venue",
        }
        friendly = [display_names.get(f, f) for f in ambiguous]
        lines.append(
            f"\n<i>Note: Some data may be incomplete ({', '.join(friendly)}). "
            "Please review carefully.</i>"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 2: Bet recommendation formatter (D-13, D-15, D-16)
# ---------------------------------------------------------------------------

# Human-readable labels for bet classification
_LABEL_DISPLAY: dict[str, str] = {
    "highest_win_probability": "Highest Win Probability",
    "best_value": "Best Value",
    "best_place_candidate": "Best Place Candidate",
    "no_bet": "No Bet",
}


def format_recommendation(state: dict) -> str:
    """Format Phase 2 bet recommendations as Telegram HTML.

    Produces runner cards per D-13 with name, label, bet type, EV, Kelly%,
    USDT amount, reasoning. Shows skip messages for Tier 1/2 skips.
    Adds market discrepancy notes (D-15) and sparse data warnings (D-11/ANALYSIS-04).
    Includes total exposure summary.

    CRITICAL: ALL variable strings (runner_name, reasoning, skip_reason, label, etc.)
    are escaped with html.escape() to prevent Telegram parse_mode=HTML failures
    per CLAUDE.md Common Pitfalls.

    Args:
        state: Pipeline state dict with final_bets, analysis_result, skip_signal, etc.

    Returns:
        HTML-formatted string ready to send via aiogram with parse_mode="HTML".
    """
    # ── Skip signal ──────────────────────────────────────────────────────────
    if state.get("skip_signal"):
        skip_reason = state.get("skip_reason") or "No favorable bets found"
        skip_tier = state.get("skip_tier", "?")
        return (
            f"<b>SKIP</b> — {html.escape(str(skip_reason))}\n\n"
            f"Tier {skip_tier} skip signal."
        )

    final_bets = state.get("final_bets") or []
    analysis_result = state.get("analysis_result") or {}

    # ── No bets case ─────────────────────────────────────────────────────────
    if not final_bets:
        return (
            "<b>No Bets</b>\n\n"
            "All runners are negative EV at current odds. No recommended bets."
        )

    # ── Runner cards ─────────────────────────────────────────────────────────
    lines: list[str] = ["<b>Bet Recommendations</b>"]

    total_usdt = sum(b.get("usdt_amount", 0.0) for b in final_bets)

    for bet in final_bets:
        runner_name = str(bet.get("runner_name", "Unknown"))
        runner_number = bet.get("runner_number", "?")
        label = str(bet.get("label", ""))
        label_display = _LABEL_DISPLAY.get(label, html.escape(label))
        bet_type = str(bet.get("bet_type", "win"))
        ev = bet.get("ev", 0.0)
        kelly_pct = bet.get("kelly_pct", 0.0)
        usdt_amount = bet.get("usdt_amount", 0.0)
        reasoning = str(bet.get("reasoning", ""))
        data_sparse = bet.get("data_sparse", False)

        lines.append("")
        lines.append(
            f"<b>{html.escape(runner_name)} (#{runner_number})</b>"
        )
        lines.append(f"Label: {html.escape(label_display)}")
        lines.append(f"Bet: {html.escape(bet_type)} — {usdt_amount:.2f} USDT")
        lines.append(f"EV: {ev:+.2f} | Kelly: {kelly_pct:.1f}%")
        lines.append(html.escape(reasoning))

        if data_sparse:
            lines.append("<i>[SPARSE DATA — sizing halved]</i>")

    # ── Market discrepancy notes (D-15) ──────────────────────────────────────
    discrepancy_notes = analysis_result.get("market_discrepancy_notes") or []
    if discrepancy_notes:
        lines.append("")
        lines.append("<b>Market Notes:</b>")
        for note in discrepancy_notes:
            lines.append(f"• {html.escape(str(note))}")

    # ── Total exposure summary ────────────────────────────────────────────────
    lines.append("")
    try:
        from services.stake.bankroll.repository import BankrollRepository
        from services.stake.settings import get_stake_settings
        settings = get_stake_settings()
        bankroll = BankrollRepository(settings.database_path).get_balance()
        if bankroll and bankroll > 0:
            exposure_pct = (total_usdt / bankroll) * 100
            lines.append(f"<b>Total: {total_usdt:.2f} USDT ({exposure_pct:.1f}% of bankroll)</b>")
        else:
            lines.append(f"<b>Total: {total_usdt:.2f} USDT</b>")
    except Exception:
        lines.append(f"<b>Total: {total_usdt:.2f} USDT</b>")

    return "\n".join(lines)
