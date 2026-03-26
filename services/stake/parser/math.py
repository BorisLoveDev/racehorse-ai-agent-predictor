"""
Deterministic odds math functions for the Stake advisor.

Per ARCH-01: ALL numerical calculations must be deterministic Python — never LLM.
These functions are pure (no side effects, no I/O) and fully unit-tested.

Functions:
    to_decimal            — convert any odds format to decimal representation
    implied_probability   — decimal odds -> implied win probability
    overround             — sum of implied probabilities (bookmaker margin indicator)
    recalculate_without_scratches — overround excluding scratched runners
    odds_drift_pct        — percentage change from opening to current odds
    no_vig_probability    — fair probability after removing bookmaker margin
    expected_value        — EV of a single bet given AI probability and decimal odds
    kelly_fraction        — full Kelly criterion fraction (never negative)
    bet_size_usdt         — quarter-Kelly bet size with cap and minimum enforcement
    apply_portfolio_caps  — enforce max win bets and total exposure limits
    apply_sparsity_discount — reduce bet size when research data is sparse
    place_bet_ev          — EV for a place bet using place_odds
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


# ---------------------------------------------------------------------------
# Phase 2 EV/Kelly functions — added per Plan 02-02
# All pure functions; no I/O, no LLM. Per ARCH-01.
# ---------------------------------------------------------------------------


def no_vig_probability(implied_prob: float, book_overround: float) -> float:
    """Remove bookmaker margin to get fair (no-vig) probability.

    Divides the implied probability by the overround to normalise back to
    a fair-book world where all probabilities sum to 1.0.

    Args:
        implied_prob: Implied probability from decimal odds (0 < p <= 1).
        book_overround: Overround factor (e.g. 1.15 for a 15% margin).

    Returns:
        Fair probability rounded to 6 decimal places.
        Always <= implied_prob (removing margin shrinks individual probabilities).
    """
    return round(implied_prob / book_overround, 6)


def expected_value(ai_prob: float, decimal_odds: float) -> float:
    """Calculate expected value of a bet given AI probability estimate.

    Formula: EV = ai_prob * (decimal_odds - 1) - (1 - ai_prob)
           = ai_prob * decimal_odds - 1

    Args:
        ai_prob: AI-estimated win probability (0.0 to 1.0).
        decimal_odds: Decimal odds for the bet.

    Returns:
        EV rounded to 6 decimal places.
        Positive = value bet, negative = -EV bet.
        EV of -1.0 when ai_prob=0 (lose entire stake).
    """
    return round(ai_prob * decimal_odds - 1.0, 6)


def kelly_fraction(ai_prob: float, decimal_odds: float) -> float:
    """Calculate full Kelly criterion bet fraction.

    Formula: f = (ai_prob * (decimal_odds - 1) - (1 - ai_prob)) / (decimal_odds - 1)
           = (ai_prob * decimal_odds - 1) / (decimal_odds - 1)

    Returns 0.0 for any negative-EV scenario (Kelly implies no bet).

    Args:
        ai_prob: AI-estimated win probability (0.0 to 1.0).
        decimal_odds: Decimal odds for the bet (must be > 1).

    Returns:
        Full Kelly fraction, clamped to [0.0, 1.0].
        0.0 when EV <= 0 (no bet recommended).
    """
    net_odds = decimal_odds - 1.0
    if net_odds <= 0:
        return 0.0
    ev = ai_prob * decimal_odds - 1.0
    if ev <= 0:
        return 0.0
    return max(0.0, round(ev / net_odds, 6))


def bet_size_usdt(
    bankroll: float,
    kelly_f: float,
    kelly_multiplier: float = 0.25,
    per_bet_cap_pct: float = 0.03,
    min_bet: float = 1.0,
) -> float:
    """Calculate bet size in USDT with quarter-Kelly, cap, and minimum enforcement.

    Sizing steps:
      1. raw = bankroll * kelly_f * kelly_multiplier   (fractional Kelly)
      2. capped = min(raw, bankroll * per_bet_cap_pct)  (single-bet cap)
      3. if capped < min_bet: return 0.0 (below minimum — skip bet)

    Args:
        bankroll: Current bankroll in USDT.
        kelly_f: Full Kelly fraction (output of kelly_fraction()).
        kelly_multiplier: Kelly fraction multiplier; default 0.25 (quarter-Kelly).
        per_bet_cap_pct: Maximum single bet as fraction of bankroll; default 0.03 (3%).
        min_bet: Minimum bet in USDT; bets below this are skipped; default 1.0.

    Returns:
        Bet size in USDT rounded to 2 decimal places, or 0.0 if below minimum.
    """
    if bankroll <= 0 or kelly_f <= 0:
        return 0.0
    raw = bankroll * kelly_f * kelly_multiplier
    capped = min(raw, bankroll * per_bet_cap_pct)
    if capped < min_bet:
        return 0.0
    return round(capped, 2)


def apply_portfolio_caps(
    bets: list[dict],
    bankroll: float,
    max_total_pct: float = 0.05,
    max_win_bets: int = 2,
) -> list[dict]:
    """Enforce portfolio-level bet caps on a list of bet recommendations.

    Rules applied in order:
      1. Win bets sorted by EV descending; only top max_win_bets kept.
      2. Place bets are not counted against max_win_bets limit.
      3. Total bet amount must not exceed max_total_pct * bankroll.
         Excess bets (lowest EV first) are trimmed until within budget.
      4. Any bet with amount < 1.0 USDT is dropped.

    Args:
        bets: List of bet dicts, each with at minimum:
              {"type": str, "amount": float, "ev": float}
        bankroll: Current bankroll in USDT.
        max_total_pct: Maximum total race exposure as fraction of bankroll; default 0.05.
        max_win_bets: Maximum number of win bets per race; default 2.

    Returns:
        New list of bet dicts after applying all caps (input not mutated).
    """
    if not bets:
        return []

    # Work on a copy to avoid mutating input
    result: list[dict] = [dict(b) for b in bets]

    # Step 1: Enforce max_win_bets — keep highest-EV win bets only
    win_bets = sorted(
        [b for b in result if b["type"] == "win"],
        key=lambda b: b.get("ev", 0.0),
        reverse=True,
    )
    allowed_win_ids = {id(b) for b in win_bets[:max_win_bets]}
    result = [
        b for b in result
        if b["type"] != "win" or id(b) in allowed_win_ids
    ]

    # Step 2: Enforce total exposure cap
    budget = bankroll * max_total_pct
    # Sort by EV descending to prefer best bets when trimming
    result_sorted = sorted(result, key=lambda b: b.get("ev", 0.0), reverse=True)
    kept: list[dict] = []
    total = 0.0
    for bet in result_sorted:
        if total + bet["amount"] <= budget + 1e-9:
            kept.append(bet)
            total += bet["amount"]
    result = kept

    # Step 3: Drop bets below minimum
    result = [b for b in result if b["amount"] >= 1.0]

    return result


def apply_sparsity_discount(
    amount: float,
    data_sparse: bool,
    discount: float = 0.5,
) -> float:
    """Reduce bet size when research data is sparse.

    When data is sparse (limited form, trainer stats, expert opinions),
    sizing confidence is reduced by multiplying by the discount factor.
    If the discounted amount falls below the 1.0 USDT minimum, return 0.0.

    Args:
        amount: Original bet size in USDT.
        data_sparse: True if research data is considered sparse.
        discount: Multiplier applied when data_sparse=True; default 0.5.

    Returns:
        Adjusted bet size in USDT rounded to 2 decimal places,
        or 0.0 if result falls below 1.0 USDT minimum.
    """
    if not data_sparse:
        return round(float(amount), 2)
    discounted = amount * discount
    if discounted < 1.0:
        return 0.0
    return round(discounted, 2)


def place_bet_ev(ai_place_prob: float, place_odds: float) -> float:
    """Calculate expected value for a place bet.

    Uses place_odds (not win_odds) per BET-07 requirement.
    Formula: EV = ai_place_prob * (place_odds - 1) - (1 - ai_place_prob)
           = ai_place_prob * place_odds - 1

    Args:
        ai_place_prob: AI-estimated probability of the horse placing (0.0 to 1.0).
        place_odds: Decimal odds for the place market (must be > 1).

    Returns:
        EV rounded to 6 decimal places.
        Positive = value bet, negative = -EV bet.
    """
    return round(ai_place_prob * place_odds - 1.0, 6)
