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
