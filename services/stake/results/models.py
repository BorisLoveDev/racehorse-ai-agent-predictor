"""
Pydantic models for Phase 3 results tracking and reflection.

Models:
    ParsedResult    — User-supplied race result after the event
    BetOutcome      — Evaluated outcome for a single bet
    LessonEntry     — Extracted lesson from post-race reflection
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ParsedResult(BaseModel):
    """Parsed race result provided by the user after the race.

    Users paste the result text into the bot; this model captures the
    structured interpretation of that text.

    Args:
        finishing_order: Runner numbers in finishing order (1st, 2nd, 3rd...).
        finishing_names: Runner names if numbers are not available.
        is_partial: True if only the winner is known, not the full order.
            When True, place bets cannot be evaluated.
        confidence: 'high' for clear unambiguous results, 'low' for ambiguous.
        raw_text: Original user input preserved for audit.
    """

    finishing_order: list[int] = Field(
        default_factory=list,
        description="Runner numbers in finishing order",
    )
    finishing_names: list[str] = Field(
        default_factory=list,
        description="Runner names if numbers not given",
    )
    is_partial: bool = Field(
        default=False,
        description="True if only winner known, not full order",
    )
    confidence: Literal["high", "low"] = Field(
        default="high",
        description="high=clear result, low=ambiguous",
    )
    raw_text: str = Field(
        default="",
        description="Original user input preserved for audit",
    )


class BetOutcome(BaseModel):
    """Evaluated outcome for a single bet recommendation.

    Produced by evaluate_bets() after the user provides the race result.
    Captures whether the bet won, profit/loss, and whether the bet
    could be evaluated given the available result data.

    Args:
        runner_number: Runner number (may be None if only name available).
        runner_name: Runner name.
        bet_type: 'win' or 'place'.
        amount_usdt: Stake amount in USDT.
        decimal_odds: Win odds at time of bet (for audit).
        place_odds: Place odds at time of bet (for audit).
        won: True if the bet won.
        profit_usdt: Net profit (positive) or loss (negative) in USDT.
        evaluable: False when result data insufficient to determine outcome.
    """

    runner_number: Optional[int] = None
    runner_name: str
    bet_type: str  # "win" | "place"
    amount_usdt: float
    decimal_odds: Optional[float] = None
    place_odds: Optional[float] = None
    won: bool = False
    profit_usdt: float = 0.0
    evaluable: bool = True


class LessonEntry(BaseModel):
    """A single lesson extracted by the reflection LLM after a race result.

    Used by LessonsRepository to persist extracted rules that inform
    future race analysis via the mindset prompt.

    Args:
        error_tag: Short category label, e.g. 'overconfidence_on_short_odds'.
        rule_sentence: One actionable rule sentence.
        is_failure_mode: True = what went wrong; False = positive principle.
    """

    error_tag: str = Field(
        description="1-line category e.g. 'overconfidence_on_short_odds'",
    )
    rule_sentence: str = Field(
        description="1 actionable rule sentence",
    )
    is_failure_mode: bool = Field(
        description="True if failure mode, False if positive rule",
    )
