"""reflection_update (spec shaft 11a + 10 audit finalisation).

Phase 1: simple append. Delegates to a writer object with an async .run(**kwargs)
method — the actual ReflectionWriter adapter is wired in Task 22.

When an audit recorder is present for this race, finalise it and persist via
AuditTracesRepository. Trace persistence runs even when skip_signal is set,
because audit reproducibility checks rely on every race having a trace.
"""
from typing import Optional

from services.stake.pipeline.state import PipelineState


def make_reflection_update_node(
    *,
    writer=None,
    traces_repo=None,
    recorder_provider=None,
):
    async def reflection_update_node(state: PipelineState) -> dict:
        race_id = state.get("race_id")
        # Audit trace finalisation runs ALWAYS (skip or not).
        if recorder_provider is not None and traces_repo is not None:
            recorder = recorder_provider(race_id)
            if recorder is not None:
                trace = recorder.finalise()
                traces_repo.save(trace)

        if state.get("skip_signal"):
            return {}
        if writer is None:
            return {}

        slip_ids = list(state.get("bet_slip_ids") or [])
        summary = await writer.run(
            race_id=race_id,
            parsed_race=state.get("parsed_race") or {},
            probabilities=state.get("probabilities") or [],
            bet_slip_ids=slip_ids,
            evidence_bet_ids=slip_ids,
            result_outcome=state.get("result_outcome") or {},
            settlement_pnl=float(state.get("settlement_pnl") or 0.0),
        )
        return {"reflection_summary": summary}

    return reflection_update_node
