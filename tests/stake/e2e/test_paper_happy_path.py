"""E2E happy-path scenarios for the Phase 1 race super-graph.

The identity calibrator would produce p_calibrated == p_market (edge=0 =>
stake=0 => decision_maker Tier-2 skip), so we plug in StubShiftCalibrator
which sharpens the distribution enough to push the favourite's edge above
min_edge_pp=3.0 and exercise the full approval + settlement path.
"""
import pytest
from langgraph.types import Command

from tests.stake.e2e._helpers import StubShiftCalibrator


@pytest.mark.asyncio
async def test_happy_path_paper_approval_accept(scenario_factory):
    """Full happy path: parse -> gate clear -> research -> probability_model
    (with stub calibrator producing positive edge) -> analyst intent -> sizer
    positive stake -> decision auto-accept -> interrupt at approval -> resume
    with accept -> result_recorder interrupt -> resume with positions ->
    settlement applies paper PnL -> reflection_update -> END.
    """
    s = await scenario_factory(
        overround=0.05,
        calibrator=StubShiftCalibrator(shift_pp=10.0),
    )
    graph = s["graph"]
    config = {"configurable": {"thread_id": "race:R1:1"}}

    # Step 1: start — graph runs until approval interrupt.
    result = await graph.ainvoke({
        "race_id": "R1", "user_id": 1, "raw_input": "x", "source_type": "text",
    }, config=config)
    interrupts = result.get("__interrupt__") or []
    assert len(interrupts) == 1, f"expected approval interrupt, got {interrupts}"
    payload = interrupts[0].value
    assert payload["kind"] == "approval"
    assert payload["bet_slip"]["stake"] > 0
    assert payload["mode"] == "paper"

    # Samples should already be written for every runner by probability_model.
    rows = s["conn"].execute(
        "SELECT COUNT(*) FROM stake_calibration_samples WHERE race_id='R1'"
    ).fetchone()[0]
    assert rows == 3

    # Step 2: resume approval with accept.
    result2 = await graph.ainvoke(
        Command(resume={"decision": "accept"}),
        config=config,
    )
    interrupts2 = result2.get("__interrupt__") or []
    assert len(interrupts2) == 1
    payload2 = interrupts2[0].value
    assert payload2["kind"] == "result_request"

    # Bet slip persisted as confirmed.
    slip_rows = s["conn"].execute(
        "SELECT status, stake FROM stake_bet_slips WHERE race_id='R1'"
    ).fetchall()
    assert len(slip_rows) == 1
    assert slip_rows[0][0] == "confirmed"
    assert float(slip_rows[0][1]) > 0

    # Step 3: resume result_recorder with positions — horse 3 wins.
    result3 = await graph.ainvoke(
        Command(resume={"positions": {3: 1, 2: 2, 1: 3}}),
        config=config,
    )
    assert not (result3.get("__interrupt__") or [])
    # Settlement PnL > 0 since horse 3 (our bet) won.
    assert result3.get("settlement_pnl", 0.0) > 0

    # Samples now have outcome filled: horse 3 won (1), others lost (0).
    outcomes = dict(s["conn"].execute(
        "SELECT horse_no, outcome FROM stake_calibration_samples "
        "WHERE race_id='R1' ORDER BY horse_no"
    ).fetchall())
    assert outcomes == {1: 0, 2: 0, 3: 1}

    # Reflection writer was invoked exactly once.
    s["reflection_writer"].run.assert_awaited_once()


@pytest.mark.asyncio
async def test_happy_path_loss_subtracts_stake(scenario_factory):
    """Same flow as the accept test, but horse 3 finishes 3rd -> loss -> PnL < 0."""
    s = await scenario_factory(
        overround=0.05,
        calibrator=StubShiftCalibrator(shift_pp=10.0),
    )
    graph = s["graph"]
    config = {"configurable": {"thread_id": "race:R2:1"}}
    await graph.ainvoke({
        "race_id": "R2", "user_id": 1, "raw_input": "x", "source_type": "text",
    }, config=config)
    await graph.ainvoke(Command(resume={"decision": "accept"}), config=config)
    result = await graph.ainvoke(
        Command(resume={"positions": {1: 1, 2: 2, 3: 3}}),
        config=config,
    )
    assert result.get("settlement_pnl", 0.0) < 0
