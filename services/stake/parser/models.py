"""
Pydantic models for parsed Stake.com race data.

These models define the data contracts shared across the entire Stake advisor
pipeline — from parsing raw paste text through analysis to bet recommendation.

Per D-07 and D-08: all fields are optional except number and name on RunnerInfo,
to accommodate incomplete Stake.com paste data gracefully.
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class RunnerInfo(BaseModel):
    """Represents a single runner (horse) in a race."""

    number: int
    name: str
    barrier: Optional[int] = None
    weight: Optional[str] = None
    jockey: Optional[str] = None
    trainer: Optional[str] = None
    form_string: Optional[str] = None
    opening_odds: Optional[float] = None
    win_odds: Optional[float] = None
    win_odds_format: Optional[Literal["decimal", "fractional", "american"]] = None
    place_odds: Optional[float] = None
    place_odds_format: Optional[Literal["decimal", "fractional", "american"]] = None
    status: Literal["active", "scratched"] = "active"
    tags: Optional[List[str]] = None
    running_style: Optional[str] = None
    market_rank: Optional[int] = None
    tips_text: Optional[str] = None


class MarketContext(BaseModel):
    """Market-level context extracted from a Stake.com race page."""

    big_bet_activity: Optional[List[str]] = None
    user_activity: Optional[str] = None
    bet_slip_info: Optional[str] = None


class ParsedRace(BaseModel):
    """
    Full parsed representation of a Stake.com horse race.

    All fields are optional to handle partial paste data gracefully.
    The LLM extraction step fills what it can; downstream steps handle gaps.
    """

    platform: Optional[str] = None
    sport: Optional[str] = None
    region: Optional[str] = None
    track: Optional[str] = None
    race_number: Optional[str] = None
    race_name: Optional[str] = None
    date: Optional[str] = None
    distance: Optional[str] = None
    surface: Optional[str] = None
    time_to_start: Optional[str] = None
    runner_count: Optional[int] = None
    bet_types_available: Optional[List[str]] = None
    place_terms: Optional[str] = None
    runners: List[RunnerInfo] = Field(default_factory=list)
    market_context: Optional[MarketContext] = None
    detected_bankroll: Optional[float] = None

    # Anti-hallucination contract (invariant I3).
    # raw_excerpts: per must-have field, a non-empty substring quoted from the
    # input. Absent or empty excerpt => field is treated as missing and the
    # validator adds it to missing_fields, routing the race to interrupt_gate.
    raw_excerpts: dict[str, str] = Field(default_factory=dict)
    field_confidences: dict[str, float] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    parser_model: Optional[str] = None
    snapshot_ts: Optional[str] = None
    source_type: Optional[str] = None  # "text" | "screenshot" | "photo" | "voice"
