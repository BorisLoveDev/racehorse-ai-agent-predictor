"""
Phase 2 data contract models for the Stake Advisor Bot.

These Pydantic models define the interfaces between Phase 2 pipeline nodes:
  - ResearchResult / ResearchOutput: output from the research step (D-02, D-03, D-04)
  - RunnerAnalysis / AnalysisResult: output from the analysis/EV step (D-07, D-08, D-13, D-14)
  - BetRecommendation: final sized bet recommendation sent to Telegram (D-13, BET-06)

Downstream plans (02, 03, 04) implement against these contracts.
Interface-first ordering prevents scavenger hunts.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ResearchResult(BaseModel):
    """Research findings for a single runner.

    Produced by the research node (SEARCH-01, SEARCH-02).
    Per D-02, D-04: captures form, trainer, expert opinion, and data quality signal.
    """

    runner_name: str
    data_quality: Literal["rich", "sparse", "none"] = Field(
        description="Research completeness signal: rich=good data, sparse=limited, none=nothing found"
    )
    form_summary: str = Field(
        description="Recent form narrative for this runner"
    )
    trainer_stats: str = Field(
        description="Trainer information and statistics"
    )
    expert_opinion: str = Field(
        description="Tips and expert views from research sources"
    )
    external_odds: Optional[str] = Field(
        default=None,
        description="Odds from external sources (TAB, Betfair, etc.) for market comparison (ANALYSIS-05)"
    )
    confidence_notes: str = Field(
        description="Data reliability notes — how trustworthy is this research"
    )


class ResearchOutput(BaseModel):
    """Aggregated research output for all runners in a race.

    Produced by the research node (D-02, D-03).
    Contains per-runner results plus overall race context.
    """

    runners: list[ResearchResult]
    overall_notes: str = Field(
        description="General race context gathered from research (track bias, conditions, etc.)"
    )


class RunnerAnalysis(BaseModel):
    """AI analysis result for a single runner.

    Produced by the analysis node (D-13, ANALYSIS-01).
    Contains AI-assigned probabilities and label for bet sizing.
    """

    runner_name: str
    runner_number: int
    label: Literal["highest_win_probability", "best_value", "best_place_candidate", "no_bet"] = Field(
        description="Runner classification for bet type selection"
    )
    ai_win_prob: float = Field(
        ge=0.0,
        le=1.0,
        description="AI-assigned win probability (0.0-1.0) for EV calculation"
    )
    ai_place_prob: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="AI-assigned place probability (0.0-1.0), if estimated"
    )
    reasoning: str = Field(
        description="2-3 sentence explanation of the AI's assessment (D-14)"
    )


ExoticMarket = Literal[
    "win", "place",
    "quinella", "exacta", "exacta_box",
    "trifecta", "trifecta_box",
    "first4", "first4_box",
    "qps", "double", "quaddie",
]


class ExoticRecommendation(BaseModel):
    """Structured exotic bet idea the AI picks from bet_types_available.

    The analyst is given the full bet-type pool available on Stake.com for
    THIS race (via parsed_race.bet_types_available) and returns one record
    per exotic it wants to suggest. Sizing is NOT computed here — legacy
    sizer only handles win/place straight bets. The user places exotics
    manually for now; downstream Phase 3 wires structured exotic sizing.
    """

    market: ExoticMarket = Field(
        description="Bet type chosen from bet_types_available. Use 'win' or 'place' only when the exotic pool is unusable for this race."
    )
    selections: list[int] = Field(
        min_length=1,
        description="Horse numbers to include, in display order. For exacta/trifecta order matters; for boxes and quinellas it does not.",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="AI subjective confidence this exotic is the best play for its market (0..1)."
    )
    rationale: str = Field(
        description="One-sentence reason (<=25 words) — why this exotic now."
    )


class AnalysisResult(BaseModel):
    """Aggregated AI analysis result for the race.

    Produced by the analysis node (D-07, D-08).
    Contains per-runner analysis plus race-level skip signals and override flags.
    """

    recommendations: list[RunnerAnalysis]
    overall_skip: bool = Field(
        description="Tier 2 skip signal — AI recommends skipping this race (D-07)"
    )
    skip_reason: Optional[str] = Field(
        default=None,
        description="Why AI recommends skipping (e.g. poor data quality, no value found)"
    )
    ai_override: bool = Field(
        description="True if AI skips despite +EV existing — qualitative override (D-08)"
    )
    override_reason: Optional[str] = Field(
        default=None,
        description="Reason for AI override when skipping despite positive EV"
    )
    market_discrepancy_notes: list[str] = Field(
        default_factory=list,
        description="Notes on differences between Stake.com odds and external market odds (D-15, ANALYSIS-05)"
    )
    exotic_suggestions: list[str] = Field(
        default_factory=list,
        description=(
            "Legacy free-text exotic ideas — kept for backward compatibility. "
            "Prefer `exotic_recommendations` (structured). If both are populated, "
            "the structured field wins."
        ),
    )
    exotic_recommendations: list["ExoticRecommendation"] = Field(
        default_factory=list,
        description=(
            "Structured exotic picks chosen from the race's bet_types_available "
            "pool. The AI must output 1-3 recommendations when at least one "
            "exotic type is available and the race has >= 4 active runners. "
            "Each recommendation names a specific market, selections (horse "
            "numbers), confidence, and rationale. Surfaced even when straight "
            "win/place are -EV."
        ),
    )


class BetRecommendation(BaseModel):
    """Final sized bet recommendation for a single runner.

    Produced by the sizing node after Kelly + portfolio caps (D-13, BET-06).
    Sent to Telegram as part of the final recommendation message.
    """

    runner_name: str
    runner_number: int
    label: Literal["highest_win_probability", "best_value", "best_place_candidate", "no_bet"] = Field(
        description="Runner classification (mirrors RunnerAnalysis.label)"
    )
    bet_type: Literal["win", "place", "skip"] = Field(
        description="Bet type: win, place, or skip (no bet)"
    )
    ev: float = Field(
        description="Expected value of this bet (positive = profitable edge)"
    )
    kelly_pct: float = Field(
        description="Kelly criterion fraction as percentage before caps (e.g. 5.0 = 5%)"
    )
    usdt_amount: float = Field(
        ge=0.0,
        description="Exact USDT bet amount after Kelly, caps, and min_bet_usdt applied"
    )
    data_sparse: bool = Field(
        description="True if sparsity discount applied to sizing due to limited research data (ANALYSIS-04)"
    )
    reasoning: str = Field(
        description="Reasoning from analysis agent passed through for display"
    )
