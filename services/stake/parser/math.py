"""
Deterministic odds math functions for the Stake advisor.

Per ARCH-01: ALL numerical calculations must be deterministic Python — never LLM.
These functions are pure (no side effects, no I/O) and fully unit-tested.

Functions:
    to_decimal       — convert any odds format to decimal representation
    implied_probability — decimal odds -> implied win probability
    overround        — sum of implied probabilities (bookmaker margin indicator)
    recalculate_without_scratches — overround excluding scratched runners
    odds_drift_pct   — percentage change from opening to current odds
"""


def to_decimal(fmt: str, odds_value: float | str) -> float:
    """Convert any odds format to decimal odds.

    Args:
        fmt: One of "decimal", "fractional", "american".
        odds_value: The odds value in the given format.
            - decimal: e.g. 3.5
            - fractional: e.g. "5/2"
            - american: e.g. 250 or -200

    Returns:
        Decimal odds rounded to 4 decimal places.

    Raises:
        ValueError: If fmt is not a recognised odds format.
    """
    if fmt == "decimal":
        return round(float(odds_value), 4)
    if fmt == "fractional":
        parts = str(odds_value).split("/")
        return round(float(parts[0]) / float(parts[1]) + 1, 4)
    if fmt == "american":
        v = float(odds_value)
        if v > 0:
            return round(v / 100 + 1, 4)
        return round(100 / abs(v) + 1, 4)
    raise ValueError(f"Unknown odds format: {fmt}")


def implied_probability(decimal_odds: float) -> float:
    """Calculate implied win probability from decimal odds.

    Args:
        decimal_odds: Decimal odds (must be > 0).

    Returns:
        Implied probability rounded to 6 decimal places.
        e.g. 2.0 -> 0.5 (50%)
    """
    return round(1 / decimal_odds, 6)


def overround(decimal_odds_list: list[float]) -> float:
    """Calculate the overround (sum of implied probabilities).

    A value of 1.0 represents a perfectly fair book.
    Values > 1.0 indicate the bookmaker's margin.

    Args:
        decimal_odds_list: List of decimal odds for all runners.

    Returns:
        Overround rounded to 4 decimal places.

    Raises:
        ValueError: If the list is empty.
    """
    if not decimal_odds_list:
        raise ValueError("Cannot calculate overround from empty list")
    return round(sum(1 / o for o in decimal_odds_list), 4)


def recalculate_without_scratches(runners: list) -> float:
    """Calculate overround using only active runners with odds.

    Filters out scratched runners (status != "active") and runners
    with no win_odds, then computes the overround on the remainder.

    Args:
        runners: List of RunnerInfo objects.

    Returns:
        Overround for the active runners.

    Raises:
        ValueError: If no active runners with win_odds remain.
    """
    active_odds = [
        r.win_odds
        for r in runners
        if r.status == "active" and r.win_odds is not None
    ]
    if not active_odds:
        raise ValueError("No active runners with odds")
    return overround(active_odds)


def odds_drift_pct(opening: float | None, current: float | None) -> float | None:
    """Calculate percentage change from opening to current odds.

    A negative value means the horse has shortened (more favoured).
    A positive value means the horse has drifted (less favoured).

    Args:
        opening: Opening odds (decimal). None if not available.
        current: Current odds (decimal). None if not available.

    Returns:
        Percentage change rounded to 2 decimal places, or None if
        either input is None.
    """
    if opening is None or current is None:
        return None
    return round((current - opening) / opening * 100, 2)
