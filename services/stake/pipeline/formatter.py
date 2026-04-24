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
    for r in sorted(enriched, key=lambda r: r.get("number", 0)):
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


def _format_no_bets_analysis(state: dict, analysis_result: dict) -> str:
    """Render a useful 'no +EV bets' card instead of a blank refusal.

    User paid for the research + analysis; they deserve to see what the AI
    found even when every runner's EV was negative after the bookmaker margin.
    Shows: market margin, AI-ranked runners with probabilities + labels +
    reasoning, market-discrepancy notes, overall race context.
    """
    lines: list[str] = []

    # Header — why we're not betting
    overround_active = state.get("overround_active")
    margin_pct = None
    if overround_active is not None:
        try:
            margin_pct = (float(overround_active) - 1.0) * 100.0
        except (TypeError, ValueError):
            margin_pct = None

    lines.append("<b>No +EV bets</b>")
    if margin_pct is not None:
        lines.append(
            f"Bookmaker margin {margin_pct:.1f}% — no runner's AI probability "
            f"beats the implied price. Showing AI analysis for reference."
        )
    else:
        lines.append("No runner's AI probability beats the implied price. AI analysis below.")

    # AI-ranked runners
    recs = analysis_result.get("recommendations") or []
    active_odds: dict[int, float] = {}
    for r in (state.get("enriched_runners") or []):
        n = r.get("number")
        odds = r.get("win_odds") or r.get("decimal_odds")
        if n is not None and odds:
            try:
                active_odds[int(n)] = float(odds)
            except (TypeError, ValueError):
                pass

    def _sort_key(rec: dict) -> float:
        return -float(rec.get("ai_win_prob") or 0.0)

    ranked = sorted(
        (r for r in recs if (r.get("label") or "") != "no_bet"),
        key=_sort_key,
    )
    # Fall back to showing everyone if every runner is "no_bet" labeled
    if not ranked:
        ranked = sorted(recs, key=_sort_key)

    # Show up to 3 for readability
    top = ranked[:3]
    if top:
        lines.append("")
        lines.append("<b>AI Ranking</b> (no bet placed):")
        for rec in top:
            name = str(rec.get("runner_name") or "?")
            number = rec.get("runner_number", "?")
            label = str(rec.get("label") or "no_bet")
            label_display = _LABEL_DISPLAY.get(label, label)
            ai_win = rec.get("ai_win_prob")
            ai_place = rec.get("ai_place_prob")
            reasoning = str(rec.get("reasoning") or "").strip()

            price_line = ""
            try:
                odds = active_odds.get(int(number)) if number not in (None, "?") else None
            except (TypeError, ValueError):
                odds = None
            if odds:
                implied = 1.0 / odds
                edge_pp = (float(ai_win or 0.0) - implied) * 100.0 if ai_win is not None else None
                price_line = f"Price {odds:.2f} (implied {implied * 100:.1f}%)"
                if edge_pp is not None:
                    price_line += f" | AI edge {edge_pp:+.1f}pp"

            lines.append("")
            lines.append(f"<b>{html.escape(name)} (#{number})</b> — {html.escape(label_display)}")
            prob_bits: list[str] = []
            if ai_win is not None:
                prob_bits.append(f"AI win {float(ai_win) * 100:.1f}%")
            if ai_place is not None:
                prob_bits.append(f"place {float(ai_place) * 100:.1f}%")
            if prob_bits:
                lines.append(" | ".join(prob_bits))
            if price_line:
                lines.append(price_line)
            if reasoning:
                lines.append(html.escape(reasoning))

    # Race-level AI notes
    overall_notes = analysis_result.get("overall_notes")
    if isinstance(overall_notes, str) and overall_notes.strip():
        lines.append("")
        lines.append(f"<i>{html.escape(overall_notes.strip())}</i>")

    discrepancy_notes = analysis_result.get("market_discrepancy_notes") or []
    if discrepancy_notes:
        lines.append("")
        lines.append("<b>Market Notes:</b>")
        for note in discrepancy_notes:
            lines.append(f"• {html.escape(str(note))}")

    exotic_struct = analysis_result.get("exotic_recommendations") or []
    exotic_free = analysis_result.get("exotic_suggestions") or []
    if exotic_struct:
        lines.append("")
        lines.append("<b>Exotic Ideas</b> (not sized — place manually if you like):")
        for rec in exotic_struct:
            if not isinstance(rec, dict):
                continue
            market = str(rec.get("market") or "").replace("_", " ")
            selections = rec.get("selections") or []
            sel_str = "-".join(str(s) for s in selections)
            confidence = rec.get("confidence")
            rationale = str(rec.get("rationale") or "").strip()
            prefix = f"<b>{html.escape(market.upper())}</b> {html.escape(sel_str)}"
            if isinstance(confidence, (int, float)):
                prefix += f" (conf {float(confidence) * 100:.0f}%)"
            lines.append(f"• {prefix} — {html.escape(rationale)}")
    elif exotic_free:
        lines.append("")
        lines.append("<b>Exotic Ideas</b> (not sized — place manually if you like):")
        for hint in exotic_free:
            lines.append(f"• {html.escape(str(hint))}")

    ai_override = analysis_result.get("ai_override")
    override_reason = analysis_result.get("override_reason")
    if ai_override and isinstance(override_reason, str) and override_reason.strip():
        lines.append("")
        lines.append(f"<b>AI Override:</b> {html.escape(override_reason.strip())}")

    return "\n".join(lines)


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

    # ── No bets case — show AI analysis instead of empty "No Bets" ───────────
    if not final_bets:
        return _format_no_bets_analysis(state, analysis_result)

    # ── Runner cards ─────────────────────────────────────────────────────────
    lines: list[str] = ["<b>Bet Recommendations</b>"]

    total_usdt = sum(b.get("usdt_amount", 0.0) for b in final_bets)

    for bet in sorted(final_bets, key=lambda b: b.get("runner_number", 0)):
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
        lines.append(f"Bet: {html.escape(bet_type)} — <b>{usdt_amount:.2f} USDT</b>")
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

    # ── Exotic bet ideas ──────────────────────────────────────────────────────
    exotic_struct = analysis_result.get("exotic_recommendations") or []
    exotic_free = analysis_result.get("exotic_suggestions") or []
    if exotic_struct:
        lines.append("")
        lines.append("<b>Exotic Ideas</b> (not sized — place manually if you like):")
        for rec in exotic_struct:
            if not isinstance(rec, dict):
                continue
            market = str(rec.get("market") or "").replace("_", " ")
            selections = rec.get("selections") or []
            sel_str = "-".join(str(s) for s in selections)
            confidence = rec.get("confidence")
            rationale = str(rec.get("rationale") or "").strip()
            prefix = f"<b>{html.escape(market.upper())}</b> {html.escape(sel_str)}"
            if isinstance(confidence, (int, float)):
                prefix += f" (conf {float(confidence) * 100:.0f}%)"
            lines.append(f"• {prefix} — {html.escape(rationale)}")
    elif exotic_free:
        lines.append("")
        lines.append("<b>Exotic Ideas</b> (not sized — place manually if you like):")
        for hint in exotic_free:
            lines.append(f"• {html.escape(str(hint))}")

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
