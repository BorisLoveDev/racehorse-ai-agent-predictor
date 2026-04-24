"""result_recorder (spec shaft 9).

Phase 1: user-ping flow. TelegramGraphRunner (Task 20) schedules a reminder at
post_time + 15 min; the user replies with finishing positions. This node
interrupts the graph and waits for Command(resume={'positions': {horse_no: pos}}).

Returns result_outcome with int-coerced keys and values for settlement.
"""
from langgraph.types import interrupt

from services.stake.pipeline.state import PipelineState


def make_result_recorder_node():
    async def result_recorder_node(state: PipelineState) -> dict:
        if state.get("skip_signal") or not state.get("bet_slip_ids"):
            return {}
        response = interrupt({
            "kind": "result_request",
            "race_id": state.get("race_id"),
            "instructions": "Reply with finishing positions: 'horse_no:position' per line.",
        })
        positions_raw = (response or {}).get("positions") or {}
        positions = {int(k): int(v) for k, v in positions_raw.items()}
        return {"result_outcome": positions}
    return result_recorder_node
