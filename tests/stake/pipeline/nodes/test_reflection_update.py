import pytest
from unittest.mock import AsyncMock, MagicMock

from services.stake.pipeline.nodes.reflection_update import make_reflection_update_node


@pytest.mark.asyncio
async def test_skips_when_skip_signal_set():
    writer = MagicMock()
    writer.run = AsyncMock()
    node = make_reflection_update_node(writer=writer)
    out = await node({"skip_signal": True, "race_id": "R1"})
    writer.run.assert_not_called()
    assert out == {}


@pytest.mark.asyncio
async def test_writer_run_called_with_evidence_bet_ids():
    writer = MagicMock()
    writer.run = AsyncMock(return_value={"lessons_appended": 1})
    node = make_reflection_update_node(writer=writer)
    out = await node({
        "race_id": "R1",
        "bet_slip_ids": ["bs1", "bs2"],
        "result_outcome": {3: 1},
        "probabilities": [{"horse_no": 3, "p_market": 0.3, "p_calibrated": 0.3}],
        "parsed_race": {"track": "Sandown"},
        "settlement_pnl": 5.0,
    })
    writer.run.assert_awaited_once()
    kwargs = writer.run.await_args.kwargs
    assert kwargs["race_id"] == "R1"
    assert kwargs["bet_slip_ids"] == ["bs1", "bs2"]
    assert kwargs["evidence_bet_ids"] == ["bs1", "bs2"]
    assert kwargs["result_outcome"] == {3: 1}
    assert kwargs["settlement_pnl"] == 5.0
    assert out["reflection_summary"] == {"lessons_appended": 1}


@pytest.mark.asyncio
async def test_empty_bet_slip_ids_still_runs():
    writer = MagicMock()
    writer.run = AsyncMock(return_value={})
    node = make_reflection_update_node(writer=writer)
    out = await node({"race_id": "R1", "bet_slip_ids": [], "settlement_pnl": 0.0})
    writer.run.assert_awaited_once()
    kwargs = writer.run.await_args.kwargs
    assert kwargs["bet_slip_ids"] == []
    assert kwargs["evidence_bet_ids"] == []
    assert out["reflection_summary"] == {}


@pytest.mark.asyncio
async def test_no_writer_is_noop():
    """When writer is None the node is a pass-through (used before Task 22 wiring)."""
    node = make_reflection_update_node(writer=None)
    out = await node({"race_id": "R1", "bet_slip_ids": ["b1"]})
    assert out == {}


@pytest.mark.asyncio
async def test_traces_repo_save_when_recorder_provided():
    """If a recorder_provider returns a recorder, finalise it and save to traces_repo."""
    writer = MagicMock()
    writer.run = AsyncMock(return_value={})
    traces_repo = MagicMock()
    finalised_trace = MagicMock()
    recorder = MagicMock()
    recorder.finalise.return_value = finalised_trace
    node = make_reflection_update_node(
        writer=writer,
        traces_repo=traces_repo,
        recorder_provider=lambda race_id: recorder,
    )
    await node({"race_id": "R1", "bet_slip_ids": ["b1"]})
    recorder.finalise.assert_called_once()
    traces_repo.save.assert_called_once_with(finalised_trace)


@pytest.mark.asyncio
async def test_traces_repo_noop_when_no_recorder():
    writer = MagicMock()
    writer.run = AsyncMock(return_value={})
    traces_repo = MagicMock()
    node = make_reflection_update_node(
        writer=writer,
        traces_repo=traces_repo,
        recorder_provider=lambda race_id: None,  # no recorder for this race
    )
    await node({"race_id": "R1", "bet_slip_ids": ["b1"]})
    traces_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_skip_signal_still_saves_audit_trace():
    """Even when skip_signal short-circuits the writer call, audit trace must persist."""
    writer = MagicMock()
    writer.run = AsyncMock()
    traces_repo = MagicMock()
    finalised_trace = MagicMock()
    recorder = MagicMock()
    recorder.finalise.return_value = finalised_trace
    node = make_reflection_update_node(
        writer=writer,
        traces_repo=traces_repo,
        recorder_provider=lambda race_id: recorder,
    )
    out = await node({"skip_signal": True, "race_id": "R1"})
    writer.run.assert_not_called()
    traces_repo.save.assert_called_once_with(finalised_trace)
    assert out == {}
