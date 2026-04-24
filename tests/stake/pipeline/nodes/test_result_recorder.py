import pytest

from services.stake.pipeline.nodes.result_recorder import make_result_recorder_node


@pytest.mark.asyncio
async def test_skips_when_skip_signal_set():
    node = make_result_recorder_node()
    out = await node({"skip_signal": True, "race_id": "R1", "bet_slip_ids": ["b1"]})
    assert out == {}


@pytest.mark.asyncio
async def test_skips_when_no_bet_slip_ids():
    node = make_result_recorder_node()
    out = await node({"race_id": "R1"})
    assert out == {}
    out = await node({"race_id": "R1", "bet_slip_ids": []})
    assert out == {}


@pytest.mark.asyncio
async def test_interrupts_when_slips_exist(monkeypatch):
    import services.stake.pipeline.nodes.result_recorder as rr
    captured = {}
    def fake_interrupt(payload):
        captured["payload"] = payload
        return {"positions": {1: 1, 2: 2, 3: 3}}
    monkeypatch.setattr(rr, "interrupt", fake_interrupt)
    node = make_result_recorder_node()
    out = await node({"race_id": "R1", "bet_slip_ids": ["b1"]})
    assert captured["payload"]["kind"] == "result_request"
    assert captured["payload"]["race_id"] == "R1"
    assert out["result_outcome"] == {1: 1, 2: 2, 3: 3}


@pytest.mark.asyncio
async def test_coerces_keys_and_values_to_int(monkeypatch):
    import services.stake.pipeline.nodes.result_recorder as rr
    monkeypatch.setattr(rr, "interrupt", lambda p: {"positions": {"1": "1", "3": "2"}})
    node = make_result_recorder_node()
    out = await node({"race_id": "R1", "bet_slip_ids": ["b1"]})
    assert out["result_outcome"] == {1: 1, 3: 2}


@pytest.mark.asyncio
async def test_missing_positions_in_resume(monkeypatch):
    import services.stake.pipeline.nodes.result_recorder as rr
    monkeypatch.setattr(rr, "interrupt", lambda p: {})
    node = make_result_recorder_node()
    out = await node({"race_id": "R1", "bet_slip_ids": ["b1"]})
    assert out["result_outcome"] == {}
