"""decision_maker (spec shaft 7.5).

Phase 1: auto-accept. The ReAct cycle 7↔7.5 is deferred to Phase 2.

Rules:
  - proposed_bet_slips empty or missing => skip (Tier 2) with
    decision_rationale='phase1_no_viable_intents'.
  - All slips have stake==0 => skip with decision_rationale='phase1_zero_stake:<caps>'
    (caps deduped and sorted for stable audit trail).
  - Otherwise, pass only positive-stake slips to final_proposed_slips and set
    decision_rationale='phase1_auto_accept'.
"""
from services.stake.pipeline.state import PipelineState


def make_decision_maker_node():
    async def decision_maker_node(state: PipelineState) -> dict:
        slips = state.get("proposed_bet_slips") or []
        if not slips:
            return {
                "skip_signal": True,
                "skip_tier": 2,
                "decision_rationale": "phase1_no_viable_intents",
                "skip_reason": "no_intents_from_analyst",
            }
        positives = [s for s in slips if float(s.get("stake", 0.0)) > 0]
        if not positives:
            caps = sorted({
                c for s in slips for c in (s.get("caps_applied") or [])
            })
            return {
                "skip_signal": True,
                "skip_tier": 2,
                "decision_rationale": "phase1_zero_stake:" + ",".join(caps),
                "skip_reason": "all_stakes_zero",
            }
        return {
            "final_proposed_slips": positives,
            "decision_rationale": "phase1_auto_accept",
        }
    return decision_maker_node
