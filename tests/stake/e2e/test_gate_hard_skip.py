"""E2E gate-interrupt scenarios.

Covers two branches of the overround classifier:
  - hard_skip (overround >= win.hard_skip=0.15): options=['skip'], resume with
    skip -> Tier-1 skip signal, no bet slips persisted.
  - interrupt (win.interrupt=0.12 <= overround < win.hard_skip=0.15): options =
    ['continue','skip','ask']. With identity calibrator + continue, the sizer
    produces stake=0 and decision_maker issues Tier-2 skip.
"""
import pytest
from langgraph.types import Command


@pytest.mark.asyncio
async def test_gate_hard_skip_pauses_then_terminates(scenario_factory):
    s = await scenario_factory(
        overround=0.20,  # > win.hard_skip (0.15)
        runners=[{"number": 1, "win_odds": 2.0}],
    )
    graph = s["graph"]
    config = {"configurable": {"thread_id": "race:R1:7"}}
    result = await graph.ainvoke({
        "race_id": "R1", "user_id": 7, "raw_input": "x", "source_type": "text",
    }, config=config)

    interrupts = result.get("__interrupt__") or []
    assert len(interrupts) == 1
    payload = interrupts[0].value
    assert payload["kind"] == "gate"
    assert payload["options"] == ["skip"]

    # Resume with skip.
    result2 = await graph.ainvoke(
        Command(resume={"decision": "skip"}),
        config=config,
    )
    assert not (result2.get("__interrupt__") or [])
    assert result2.get("skip_signal") is True
    assert result2.get("skip_tier") == 1

    # No bet slips were persisted.
    n = s["conn"].execute(
        "SELECT COUNT(*) FROM stake_bet_slips WHERE race_id='R1'"
    ).fetchone()[0]
    assert n == 0


@pytest.mark.asyncio
async def test_gate_continue_proceeds_to_analysis(scenario_factory):
    """Overround in the interrupt band -> user chooses 'continue' -> graph
    runs probability/analyst/sizer with IdentityCalibrator => edge=0 => sizer
    stakes=0 => decision_maker Tier-2 skip. No approval interrupt."""
    s = await scenario_factory(overround=0.13)  # win.interrupt=0.12, hard_skip=0.15
    graph = s["graph"]
    config = {"configurable": {"thread_id": "race:R1:7"}}
    result = await graph.ainvoke({
        "race_id": "R1", "user_id": 7, "raw_input": "x", "source_type": "text",
    }, config=config)
    payload = result["__interrupt__"][0].value
    assert set(payload["options"]) == {"continue", "skip", "ask"}

    result2 = await graph.ainvoke(
        Command(resume={"decision": "continue"}),
        config=config,
    )
    assert not (result2.get("__interrupt__") or [])
    assert result2.get("skip_signal") is True
    assert result2.get("skip_tier") == 2
