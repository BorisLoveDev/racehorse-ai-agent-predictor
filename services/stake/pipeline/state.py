"""
LangGraph pipeline state definition for the Stake Advisor.

PipelineState is a TypedDict used as the shared state object passed
between nodes in the LangGraph StateGraph pipeline. Each node returns
a partial update dict; LangGraph merges them into the running state.

Per PIPELINE-01: state carries raw_input through parse -> calc nodes.
Per PIPELINE-02: ambiguous_fields drives the clarifying question flow.
Phase 2: adds research, analysis, sizing, and skip signal fields.
"""

from typing import TypedDict, Optional, List

from services.stake.parser.models import ParsedRace


class PipelineState(TypedDict, total=False):
    """Shared state object for the Stake Advisor parse pipeline.

    All fields are optional (total=False) because each node only
    populates the fields it produces; earlier fields remain unchanged
    as nodes return partial update dicts.

    Phase 1 fields:
        raw_input: Raw text pasted from Stake.com or loaded from .txt file.
        parsed_race: ParsedRace Pydantic model produced by the parse node.
        detected_bankroll: Bankroll amount extracted from paste (PARSE-03).
        active_runners: List of active (non-scratched) runner dicts.
        overround_raw: Overround across all runners with odds.
        overround_active: Overround across active runners only.
        enriched_runners: Runners with decimal_odds, implied_prob, odds_drift added.
        ambiguous_fields: Fields that couldn't be confidently parsed (PIPELINE-02).
                          Non-empty list triggers the clarifying question flow.
        error: Error message string if any node failed.

    Phase 2 fields:
        skip_signal: True = skip this race entirely (Tier 1 or Tier 2 skip).
        skip_reason: Human-readable explanation for the skip decision.
        skip_tier: 1 = pre-analysis skip (overround/Tier 1), 2 = post-analysis skip (AI/Tier 2).
        research_results: ResearchOutput.model_dump() — per-runner research data.
                          Stored as dict for Redis FSM serialisation compatibility.
        research_error: Error message if research step failed (non-fatal).
        analysis_result: AnalysisResult.model_dump() — AI analysis with probabilities.
                         Stored as dict for Redis FSM serialisation compatibility.
        final_bets: List of BetRecommendation dicts after portfolio caps applied.
                    Stored as list[dict] for Redis FSM serialisation compatibility.
        recommendation_text: Formatted recommendation message ready to send on Telegram.
    """

    # Phase 1 fields — unchanged
    raw_input: str
    parsed_race: Optional[ParsedRace]
    detected_bankroll: Optional[float]
    active_runners: Optional[List[dict]]
    overround_raw: Optional[float]
    overround_active: Optional[float]
    enriched_runners: Optional[List[dict]]
    ambiguous_fields: Optional[List[str]]
    error: Optional[str]

    # Phase 2: Research, Analysis, Sizing fields
    skip_signal: Optional[bool]           # True = skip this race
    skip_reason: Optional[str]            # Why skipping
    skip_tier: Optional[int]              # 1 = pre-analysis, 2 = post-analysis
    research_results: Optional[dict]      # ResearchOutput.model_dump()
    research_error: Optional[str]         # Error from research step
    analysis_result: Optional[dict]       # AnalysisResult.model_dump()
    final_bets: Optional[List[dict]]      # List of BetRecommendation dicts after portfolio caps
    recommendation_text: Optional[str]    # Formatted recommendation for Telegram

    # Phase 1 v1.0-spec fields
    race_id: Optional[str]
    user_id: Optional[int]
    source_type: Optional[str]                # "text" | "screenshot" | "photo" | "voice"
    probabilities: Optional[List[dict]]       # RunnerProb.model_dump() entries
    llm_adjustments: Optional[List[dict]]     # LLMAdjustment.model_dump() entries
    bet_intents: Optional[List[dict]]         # BetIntent.model_dump() entries
    proposed_bet_slips: Optional[List[dict]]  # ProposedBetSlip.model_dump() entries
    final_proposed_slips: Optional[List[dict]]  # Filtered by decision_maker
    decision_rationale: Optional[str]
    bet_slip_ids: Optional[List[str]]
    approval_decisions: Optional[List[str]]
    kill_requested: Optional[bool]
    gate_decision: Optional[str]
    gate_ask_pending: Optional[bool]
    audit_trace_id: Optional[str]
    result_outcome: Optional[dict]            # {horse_no: finishing_position}
    settlement_pnl: Optional[float]
    reflection_summary: Optional[dict]
    missing_fields: Optional[List[str]]
