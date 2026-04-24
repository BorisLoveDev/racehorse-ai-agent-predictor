"""Analyst node (spec shaft 6).

Transforms research + probability outputs into BetIntent[] + LLMAdjustment[]
via an LLM call. Validates the LLM response against invariant I2:
 - Forbids 'probability', 'p_raw', 'p_calibrated' keys on intents.
 - Forces edge_source='paper_only' on all intents in paper mode (so downstream
   sizer/decision_maker can't be tricked into treating them as live-eligible).
Raises ValueError on I2 violation; pydantic.ValidationError on schema drift.
"""
from typing import Any

from services.stake.contracts import BetIntent, LLMAdjustment
from services.stake.pipeline.state import PipelineState


_FORBIDDEN_INTENT_KEYS = {"probability", "p_raw", "p_calibrated", "p_market"}


def _postprocess_llm_output(
    raw: dict, *, paper_mode: bool,
) -> tuple[list[BetIntent], list[LLMAdjustment]]:
    intents_raw = raw.get("intents") or []
    adj_raw = raw.get("adjustments") or []
    intents: list[BetIntent] = []
    for entry in intents_raw:
        offenders = set(entry.keys()) & _FORBIDDEN_INTENT_KEYS
        if offenders:
            raise ValueError(
                f"Invariant I2 violated: LLM returned forbidden key(s) {offenders}"
            )
        if paper_mode:
            entry = {**entry, "edge_source": "paper_only"}
        intents.append(BetIntent.model_validate(entry))
    adjustments = [LLMAdjustment.model_validate(a) for a in adj_raw]
    return intents, adjustments


def make_analyst_node(*, llm_call, paper_mode: bool):
    """`llm_call`: async callable taking (payload: dict) and returning dict."""
    async def analyst_node(state: PipelineState) -> dict:
        payload = {
            "race": state.get("parsed_race"),
            "runners": state.get("enriched_runners"),
            "research": state.get("research_results"),
            "probabilities": state.get("probabilities"),
        }
        raw = await llm_call(payload)
        intents, adjustments = _postprocess_llm_output(raw, paper_mode=paper_mode)
        return {
            "bet_intents": [i.model_dump(mode="json") for i in intents],
            "llm_adjustments": [a.model_dump(mode="json") for a in adjustments],
        }
    return analyst_node
