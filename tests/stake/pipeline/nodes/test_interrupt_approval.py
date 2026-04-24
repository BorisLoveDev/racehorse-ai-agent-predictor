import pytest
from unittest.mock import MagicMock

from services.stake.pipeline.nodes.interrupt_approval import (
    build_approval_payload, make_interrupt_approval_node,
)


def _sample_slip_dict(stake: float = 2.0) -> dict:
    return {
        "intent": {"market": "win", "selections": [3], "confidence": 0.6,
                   "rationale_id": "r", "edge_source": "paper_only"},
        "stake": stake, "kelly_fraction_used": 0.25,
        "expected_return": 3.0, "expected_value": 0.2,
        "max_loss": stake, "profit_if_win": stake * 1.5, "portfolio_var_95": stake,
        "caps_applied": [], "mode": "paper",
        "sizing_params": {"kelly_fraction": 0.25, "risk_mode": "normal"},
    }


def test_build_approval_payload_shape():
    payload = build_approval_payload(
        race_id="R1", slip=_sample_slip_dict(),
        rationale="phase1_auto_accept", mode="paper", reflection_id=None,
    )
    assert payload.kind == "approval"
    assert payload.race_id == "R1"
    assert payload.mode == "paper"
    assert set(payload.options) == {"accept", "edit", "reject", "kill"}
    assert payload.bet_slip["stake"] == 2.0
    assert payload.reflection_id is None


@pytest.mark.asyncio
async def test_node_returns_empty_when_no_slips(monkeypatch):
    bankroll_repo = MagicMock()
    node = make_interrupt_approval_node(bankroll_repo=bankroll_repo, mode="paper")
    out = await node({"race_id": "R1", "user_id": 42, "final_proposed_slips": []})
    assert out == {}
    bankroll_repo.save_bet_slip.assert_not_called()


@pytest.mark.asyncio
async def test_node_persists_and_confirms_on_accept(monkeypatch):
    import services.stake.pipeline.nodes.interrupt_approval as mod
    monkeypatch.setattr(mod, "interrupt", lambda payload: {"decision": "accept"})
    bankroll_repo = MagicMock()
    node = make_interrupt_approval_node(bankroll_repo=bankroll_repo, mode="paper")
    out = await node({
        "race_id": "R1", "user_id": 42,
        "final_proposed_slips": [_sample_slip_dict()],
        "decision_rationale": "phase1_auto_accept",
    })
    assert len(out["bet_slip_ids"]) == 1
    assert out["approval_decisions"] == ["accept"]
    bankroll_repo.save_bet_slip.assert_called_once()
    bankroll_repo.update_bet_slip_status.assert_called_once()
    assert bankroll_repo.update_bet_slip_status.call_args.args[1] == "confirmed"


@pytest.mark.asyncio
async def test_node_cancels_on_reject(monkeypatch):
    import services.stake.pipeline.nodes.interrupt_approval as mod
    monkeypatch.setattr(mod, "interrupt", lambda p: {"decision": "reject"})
    bankroll_repo = MagicMock()
    node = make_interrupt_approval_node(bankroll_repo=bankroll_repo, mode="paper")
    out = await node({
        "race_id": "R1", "user_id": 42,
        "final_proposed_slips": [_sample_slip_dict()],
        "decision_rationale": "r",
    })
    assert out["approval_decisions"] == ["reject"]
    assert bankroll_repo.update_bet_slip_status.call_args.args[1] == "cancelled"


@pytest.mark.asyncio
async def test_node_halts_on_kill(monkeypatch):
    import services.stake.pipeline.nodes.interrupt_approval as mod
    monkeypatch.setattr(mod, "interrupt", lambda p: {"decision": "kill"})
    bankroll_repo = MagicMock()
    node = make_interrupt_approval_node(bankroll_repo=bankroll_repo, mode="paper")
    # Two slips — node should halt after first kill
    out = await node({
        "race_id": "R1", "user_id": 42,
        "final_proposed_slips": [_sample_slip_dict(), _sample_slip_dict(stake=3.0)],
        "decision_rationale": "r",
    })
    assert out["kill_requested"] is True
    assert len(out["bet_slip_ids"]) == 1   # only first slip created
    assert out["approval_decisions"] == ["kill"]


@pytest.mark.asyncio
async def test_node_edit_stores_details_in_user_edits(monkeypatch):
    import services.stake.pipeline.nodes.interrupt_approval as mod
    monkeypatch.setattr(mod, "interrupt",
                        lambda p: {"decision": "edit", "details": {"stake": 1.5}})
    bankroll_repo = MagicMock()
    node = make_interrupt_approval_node(bankroll_repo=bankroll_repo, mode="paper")
    await node({
        "race_id": "R1", "user_id": 42,
        "final_proposed_slips": [_sample_slip_dict()],
        "decision_rationale": "r",
    })
    # edit => status=confirmed, user_edits={stake: 1.5}
    status = bankroll_repo.update_bet_slip_status.call_args.args[1]
    user_edits = bankroll_repo.update_bet_slip_status.call_args.kwargs.get("user_edits")
    assert status == "confirmed"
    assert user_edits == {"stake": 1.5}


@pytest.mark.asyncio
async def test_node_multiple_slips_sequential_interrupts(monkeypatch):
    """Each positive slip gets its own interrupt() in order."""
    responses = iter([{"decision": "accept"}, {"decision": "reject"}])
    import services.stake.pipeline.nodes.interrupt_approval as mod
    monkeypatch.setattr(mod, "interrupt", lambda p: next(responses))
    bankroll_repo = MagicMock()
    node = make_interrupt_approval_node(bankroll_repo=bankroll_repo, mode="paper")
    out = await node({
        "race_id": "R1", "user_id": 42,
        "final_proposed_slips": [_sample_slip_dict(), _sample_slip_dict(stake=4.0)],
        "decision_rationale": "r",
    })
    assert out["approval_decisions"] == ["accept", "reject"]
    assert len(out["bet_slip_ids"]) == 2
