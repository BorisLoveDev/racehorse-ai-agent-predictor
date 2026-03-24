"""
LangGraph pipeline state definition for the Stake Advisor.

PipelineState is a TypedDict used as the shared state object passed
between nodes in the LangGraph StateGraph pipeline. Each node returns
a partial update dict; LangGraph merges them into the running state.

Per PIPELINE-01: state carries raw_input through parse -> calc nodes.
Per PIPELINE-02: ambiguous_fields drives the clarifying question flow.
"""

from typing import TypedDict, Optional, List

from services.stake.parser.models import ParsedRace


class PipelineState(TypedDict, total=False):
    """Shared state object for the Stake Advisor parse pipeline.

    All fields are optional (total=False) because each node only
    populates the fields it produces; earlier fields remain unchanged
    as nodes return partial update dicts.

    Fields:
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
    """

    raw_input: str
    parsed_race: Optional[ParsedRace]
    detected_bankroll: Optional[float]
    active_runners: Optional[List[dict]]
    overround_raw: Optional[float]
    overround_active: Optional[float]
    enriched_runners: Optional[List[dict]]
    ambiguous_fields: Optional[List[str]]
    error: Optional[str]
