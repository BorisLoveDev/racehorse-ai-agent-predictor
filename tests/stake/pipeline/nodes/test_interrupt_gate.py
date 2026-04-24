import pytest

from services.stake.config.models import PhaseOneSettings
from services.stake.pipeline.nodes.interrupt_gate import (
    classify_overround, _run_gate_check, make_interrupt_gate_node,
)


def test_classify_win_below_interrupt_is_clear():
    assert classify_overround(market="win", overround=0.08, settings=PhaseOneSettings()) == "clear"


def test_classify_win_at_interrupt_is_interrupt():
    # win.interrupt = 0.12 exactly trips
    assert classify_overround(market="win", overround=0.12, settings=PhaseOneSettings()) == "interrupt"


def test_classify_win_between_is_interrupt():
    assert classify_overround(market="win", overround=0.13, settings=PhaseOneSettings()) == "interrupt"


def test_classify_win_above_hard_skip():
    # win.hard_skip = 0.15 exactly trips
    assert classify_overround(market="win", overround=0.15, settings=PhaseOneSettings()) == "hard_skip"
    assert classify_overround(market="win", overround=0.20, settings=PhaseOneSettings()) == "hard_skip"


def test_classify_place_uses_place_thresholds():
    s = PhaseOneSettings()
    assert classify_overround(market="place", overround=0.14, settings=s) == "clear"
    assert classify_overround(market="place", overround=0.17, settings=s) == "interrupt"
    assert classify_overround(market="place", overround=0.20, settings=s) == "hard_skip"


def test_classify_quinella_uses_qe_bucket():
    s = PhaseOneSettings()
    assert classify_overround(market="quinella", overround=0.16, settings=s) == "clear"
    assert classify_overround(market="exacta", overround=0.18, settings=s) == "interrupt"
    assert classify_overround(market="exacta", overround=0.20, settings=s) == "hard_skip"


def test_classify_trifecta_uses_tri_bucket():
    s = PhaseOneSettings()
    assert classify_overround(market="trifecta", overround=0.25, settings=s) == "clear"
    assert classify_overround(market="trifecta", overround=0.30, settings=s) == "interrupt"
    assert classify_overround(market="first4", overround=0.40, settings=s) == "hard_skip"


def test_classify_unknown_market_falls_back_to_win():
    # Defensive: unknown market uses win bucket (conservative).
    s = PhaseOneSettings()
    assert classify_overround(market="bogus", overround=0.05, settings=s) == "clear"
    assert classify_overround(market="bogus", overround=0.20, settings=s) == "hard_skip"


def test_run_gate_check_clear_returns_none():
    s = PhaseOneSettings()
    payload = _run_gate_check(
        settings=s, race_id="R1", market="win",
        overround=0.05, missing_fields=[],
    )
    assert payload is None


def test_run_gate_check_interrupt_has_three_options():
    s = PhaseOneSettings()
    payload = _run_gate_check(
        settings=s, race_id="R1", market="win",
        overround=0.13, missing_fields=[],
    )
    assert payload is not None
    assert payload.kind == "gate"
    assert set(payload.options) == {"continue", "skip", "ask"}
    assert "overround" in payload.reason


def test_run_gate_check_hard_skip_only_skip_option():
    s = PhaseOneSettings()
    payload = _run_gate_check(
        settings=s, race_id="R1", market="win",
        overround=0.20, missing_fields=[],
    )
    assert payload is not None
    assert payload.options == ["skip"]
    assert "hard_skip" in payload.reason


def test_run_gate_check_missing_fields_trigger_interrupt_even_if_clear():
    s = PhaseOneSettings()
    payload = _run_gate_check(
        settings=s, race_id="R1", market="win",
        overround=0.05, missing_fields=["distance", "date"],
    )
    assert payload is not None
    assert set(payload.options) == {"continue", "skip", "ask"}
    assert "distance" in payload.reason
    assert payload.missing_fields == ["distance", "date"]


def test_run_gate_check_hard_skip_overrides_missing_fields():
    s = PhaseOneSettings()
    payload = _run_gate_check(
        settings=s, race_id="R1", market="win",
        overround=0.20, missing_fields=["distance"],
    )
    assert payload is not None
    assert payload.options == ["skip"]


@pytest.mark.asyncio
async def test_gate_node_passes_through_on_clear(monkeypatch):
    # When payload is None, node returns {} and does NOT call interrupt()
    import services.stake.pipeline.nodes.interrupt_gate as gate_mod
    interrupt_called = []
    monkeypatch.setattr(gate_mod, "interrupt",
                        lambda payload: interrupt_called.append(payload))
    node = make_interrupt_gate_node(PhaseOneSettings())
    out = await node({
        "race_id": "R1",
        "overround_active": 0.05,
        "missing_fields": [],
    })
    assert out == {}
    assert interrupt_called == []


@pytest.mark.asyncio
async def test_gate_node_skip_on_hard_skip(monkeypatch):
    import services.stake.pipeline.nodes.interrupt_gate as gate_mod
    # interrupt() returns user's resume decision; for hard_skip the payload has
    # only options=['skip'], but we still call interrupt() so the UI shows the
    # reason. User responds with 'skip'.
    monkeypatch.setattr(gate_mod, "interrupt", lambda payload: {"decision": "skip"})
    node = make_interrupt_gate_node(PhaseOneSettings())
    out = await node({
        "race_id": "R1",
        "overround_active": 0.20,
        "missing_fields": [],
    })
    assert out["skip_signal"] is True
    assert out["skip_tier"] == 1


@pytest.mark.asyncio
async def test_gate_node_continue_sets_gate_decision(monkeypatch):
    import services.stake.pipeline.nodes.interrupt_gate as gate_mod
    monkeypatch.setattr(gate_mod, "interrupt", lambda payload: {"decision": "continue"})
    node = make_interrupt_gate_node(PhaseOneSettings())
    out = await node({
        "race_id": "R1",
        "overround_active": 0.13,
        "missing_fields": [],
    })
    assert out.get("skip_signal") is not True
    assert out["gate_decision"] == "continue"


@pytest.mark.asyncio
async def test_gate_node_ask_sets_pending_flag(monkeypatch):
    import services.stake.pipeline.nodes.interrupt_gate as gate_mod
    monkeypatch.setattr(gate_mod, "interrupt", lambda payload: {"decision": "ask"})
    node = make_interrupt_gate_node(PhaseOneSettings())
    out = await node({
        "race_id": "R1",
        "overround_active": 0.13,
        "missing_fields": ["distance"],
    })
    assert out.get("skip_signal") is not True
    assert out["gate_ask_pending"] is True
