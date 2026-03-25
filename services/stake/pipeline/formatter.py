"""
Race summary formatter for Telegram display.

Formats parsed and enriched pipeline state as HTML for aiogram messages.
Per D-17, D-18, D-21: shows track, race number, distance, surface, place terms,
runners with odds/probability/drift, overround margin, and ambiguous data warnings.

Exported:
    format_race_summary(state: PipelineState) -> str
"""

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
