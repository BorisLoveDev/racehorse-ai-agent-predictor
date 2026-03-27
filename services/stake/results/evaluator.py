"""
Pure-Python P&L evaluator for bet recommendations against race results.

Per ARCH-01: all numerical calculations are deterministic Python — no LLM calls.

Functions:
    evaluate_bets   — Evaluate a list of bet dicts against a ParsedResult
"""

from services.stake.results.models import BetOutcome, ParsedResult


def evaluate_bets(
    final_bets: list[dict],
    result: ParsedResult,
) -> list[BetOutcome]:
    """Evaluate bet recommendations against a race result.

    Computes P&L for each bet using the following rules:

    Win bet:
        - evaluable=True if winner is known (finishing_order non-empty)
        - won = True if runner_number == finishing_order[0]
        - profit = (amount * decimal_odds - amount) if won else -amount

    Place bet:
        - evaluable=False if result.is_partial (only winner known)
        - evaluable=False if place_odds is None
        - won = True if runner_number in finishing_order[:3]
        - profit = (amount * place_odds - amount) if won else -amount

    Per ARCH-01: pure Python, no LLM calls.

    Args:
        final_bets: List of bet dicts from sizing_node. Each dict should have:
            runner_name, runner_number, bet_type, usdt_amount,
            decimal_odds (optional), place_odds (optional).
        result: ParsedResult with finishing_order and is_partial.

    Returns:
        List of BetOutcome, one per input bet.
    """
    outcomes: list[BetOutcome] = []

    winner: int | None = result.finishing_order[0] if result.finishing_order else None
    top_3: set[int] = set(result.finishing_order[:3])

    for bet in final_bets:
        runner_number: int | None = bet.get("runner_number")
        runner_name: str = bet.get("runner_name", "")
        bet_type: str = bet.get("bet_type", "win")
        amount: float = float(bet.get("usdt_amount", 0.0))
        decimal_odds: float | None = bet.get("decimal_odds")
        place_odds: float | None = bet.get("place_odds")

        won = False
        profit = 0.0
        evaluable = True

        if bet_type == "win":
            if winner is None:
                # Cannot evaluate — no result available
                evaluable = False
            else:
                won = runner_number is not None and runner_number == winner
                if won and decimal_odds is not None:
                    profit = round(amount * decimal_odds - amount, 4)
                else:
                    profit = round(-amount, 4) if not won else 0.0

        elif bet_type == "place":
            if result.is_partial:
                # Only winner known — cannot evaluate place positions
                evaluable = False
            elif place_odds is None:
                # No place odds stored — cannot compute P&L
                evaluable = False
            else:
                won = runner_number is not None and runner_number in top_3
                if won:
                    profit = round(amount * place_odds - amount, 4)
                else:
                    profit = round(-amount, 4)

        outcomes.append(
            BetOutcome(
                runner_number=runner_number,
                runner_name=runner_name,
                bet_type=bet_type,
                amount_usdt=amount,
                decimal_odds=decimal_odds,
                place_odds=place_odds,
                won=won,
                profit_usdt=profit,
                evaluable=evaluable,
            )
        )

    return outcomes
