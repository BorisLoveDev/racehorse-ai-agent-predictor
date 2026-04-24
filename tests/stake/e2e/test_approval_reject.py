"""E2E scenarios for approval rejection and kill.

Both paths persist the bet slip in 'draft' before the interrupt fires, then
transition to 'cancelled' when the user resumes with reject or kill. In Phase
1 the graph still flows to result_recorder afterwards (the slip list remains
non-empty) which lets us validate the DB state in the same run.
"""
import pytest
from langgraph.types import Command

from tests.stake.e2e._helpers import StubShiftCalibrator


@pytest.mark.asyncio
async def test_approval_reject_marks_slip_cancelled(scenario_factory):
    s = await scenario_factory(
        overround=0.05,
        calibrator=StubShiftCalibrator(shift_pp=10.0),
    )
    graph = s["graph"]
    config = {"configurable": {"thread_id": "race:R1:9"}}
    result = await graph.ainvoke({
        "race_id": "R1", "user_id": 9, "raw_input": "x", "source_type": "text",
    }, config=config)
    assert result["__interrupt__"][0].value["kind"] == "approval"

    # Resume with reject.
    await graph.ainvoke(
        Command(resume={"decision": "reject"}),
        config=config,
    )

    slip_rows = s["conn"].execute(
        "SELECT status FROM stake_bet_slips WHERE race_id='R1'"
    ).fetchall()
    assert len(slip_rows) == 1
    assert slip_rows[0][0] == "cancelled"


@pytest.mark.asyncio
async def test_approval_kill_halts_pipeline(scenario_factory):
    """Kill on approval sets kill_requested; graph proceeds to result_recorder
    (bet_slip_ids non-empty) which interrupts for positions. Verify the slip
    status is cancelled regardless."""
    s = await scenario_factory(
        overround=0.05,
        calibrator=StubShiftCalibrator(shift_pp=10.0),
    )
    graph = s["graph"]
    config = {"configurable": {"thread_id": "race:R1:9"}}
    await graph.ainvoke({
        "race_id": "R1", "user_id": 9, "raw_input": "x", "source_type": "text",
    }, config=config)
    await graph.ainvoke(
        Command(resume={"decision": "kill"}),
        config=config,
    )

    rows = s["conn"].execute(
        "SELECT status FROM stake_bet_slips WHERE race_id='R1'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "cancelled"
