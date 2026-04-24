"""interrupt_gate (spec shaft 3) — Tier-1 pre-analysis gate.

Classifies overround per market, optionally combined with missing must-have
fields from the parser validator (Task 6). If either trigger fires, emits an
InterruptGatePayload via langgraph.interrupt() and waits for the user's
Command(resume={"decision": ...}).

Phase 1 defaults to the 'win' market when none is specified — place/exotics
get their own classifier calls from downstream nodes when they start matter.
"""
from typing import Literal, Optional

from langgraph.types import interrupt

from services.stake.config.models import OverroundThreshold, PhaseOneSettings
from services.stake.pipeline.interrupts import (
    InterruptGatePayload, InterruptResume,
)
from services.stake.pipeline.state import PipelineState


GateVerdict = Literal["clear", "interrupt", "hard_skip"]


def _thresholds_for(market: str, settings: PhaseOneSettings) -> OverroundThreshold:
    ob = settings.thresholds.overround
    if market == "win":
        return ob.win
    if market == "place":
        return ob.place
    if market in ("quinella", "exacta"):
        return ob.quinella_exacta
    if market in ("trifecta", "trifecta_box", "first4"):
        return ob.trifecta_first4
    return ob.win  # unknown market — conservative fallback


def classify_overround(
    *, market: str, overround: float, settings: PhaseOneSettings,
) -> GateVerdict:
    t = _thresholds_for(market, settings)
    if overround >= t.hard_skip:
        return "hard_skip"
    if overround >= t.interrupt:
        return "interrupt"
    return "clear"


def _run_gate_check(
    *,
    settings: PhaseOneSettings,
    race_id: str,
    market: str,
    overround: float,
    missing_fields: list[str],
) -> Optional[InterruptGatePayload]:
    verdict = classify_overround(market=market, overround=overround, settings=settings)
    if verdict == "clear" and not missing_fields:
        return None
    if verdict == "hard_skip":
        return InterruptGatePayload(
            race_id=race_id,
            reason=f"overround_{overround:.3f}_hard_skip",
            overround=overround,
            missing_fields=missing_fields,
            options=["skip"],
        )
    # interrupt or clear-but-missing-fields
    reason_bits: list[str] = []
    if verdict == "interrupt":
        reason_bits.append(f"overround_{overround:.3f}")
    if missing_fields:
        reason_bits.append(f"missing:{','.join(missing_fields)}")
    return InterruptGatePayload(
        race_id=race_id,
        reason="|".join(reason_bits) or "user_review",
        overround=overround,
        missing_fields=missing_fields,
        options=["continue", "skip", "ask"],
    )


def make_interrupt_gate_node(settings: PhaseOneSettings):
    async def interrupt_gate_node(state: PipelineState) -> dict:
        race_id = state.get("race_id") or "unknown"
        overround_active = state.get("overround_active") or 0.0
        missing = list(state.get("missing_fields") or [])
        payload = _run_gate_check(
            settings=settings, race_id=race_id, market="win",
            overround=float(overround_active), missing_fields=missing,
        )
        if payload is None:
            return {}
        response = interrupt(payload.model_dump(mode="json"))
        resume = InterruptResume.model_validate(response)
        if resume.decision == "skip":
            return {
                "skip_signal": True,
                "skip_tier": 1,
                "skip_reason": payload.reason,
            }
        if resume.decision == "ask":
            return {"gate_ask_pending": True}
        # continue
        return {"gate_decision": "continue"}
    return interrupt_gate_node
