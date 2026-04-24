import pytest
from unittest.mock import AsyncMock, MagicMock

from services.stake.telegram_bridge.runner import TelegramGraphRunner


class _FakeInterrupt:
    """LangGraph Interrupt duck-type — carries a .value."""
    def __init__(self, value): self.value = value


@pytest.mark.asyncio
async def test_start_race_dispatches_gate_card():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={
        "__interrupt__": [_FakeInterrupt({
            "kind": "gate", "race_id": "R1", "reason": "overround_0.14",
            "overround": 0.14, "missing_fields": [],
            "options": ["continue", "skip", "ask"],
        })]
    })
    send_card = AsyncMock()
    send_skip = AsyncMock()
    send_result_request = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card,
                                 send_skip=send_skip,
                                 send_result_request=send_result_request)
    await runner.start_race(user_id=42, race_id="R1", raw_text="x")
    send_card.assert_awaited_once()
    call = send_card.await_args
    assert call.kwargs["user_id"] == 42
    assert call.kwargs["payload"]["kind"] == "gate"


@pytest.mark.asyncio
async def test_start_race_terminal_skip_sends_skip_card():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={
        "skip_signal": True, "skip_reason": "overround_0.20",
    })
    send_card = AsyncMock(); send_skip = AsyncMock(); send_result = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card, send_skip=send_skip,
                                 send_result_request=send_result)
    await runner.start_race(user_id=42, race_id="R1", raw_text="x")
    send_skip.assert_awaited_once_with(user_id=42, race_id="R1",
                                       reason="overround_0.20")
    send_card.assert_not_called()


@pytest.mark.asyncio
async def test_on_callback_resumes_graph():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"skip_signal": False})
    send_card = AsyncMock(); send_skip = AsyncMock(); send_result = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card, send_skip=send_skip,
                                 send_result_request=send_result)
    cb = {"kind": "gate", "decision": "continue", "race_id": "R1", "slip_idx": None}
    await runner.on_callback(user_id=42, cb=cb)
    # ainvoke called with Command-like resume payload
    call = graph.ainvoke.await_args
    from langgraph.types import Command
    assert isinstance(call.args[0], Command)
    # thread_id in config matches convention race:R1:42
    cfg = call.kwargs.get("config") or call.args[1]
    assert cfg == {"configurable": {"thread_id": "race:R1:42"}}


@pytest.mark.asyncio
async def test_on_callback_sends_approval_card_if_graph_interrupts_again():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={
        "__interrupt__": [_FakeInterrupt({
            "kind": "approval", "race_id": "R1", "mode": "paper",
            "rationale": "phase1_auto_accept", "reflection_id": None,
            "bet_slip": {"intent": {"market": "win", "selections": [3],
                                    "confidence": 0.6, "rationale_id": "r",
                                    "edge_source": "paper_only"},
                         "stake": 2.0, "kelly_fraction_used": 0.25,
                         "expected_return": 5.0, "expected_value": 0.3,
                         "max_loss": 2.0, "profit_if_win": 3.0,
                         "portfolio_var_95": 2.0, "caps_applied": [], "mode": "paper",
                         "sizing_params": {"kelly_fraction": 0.25, "risk_mode": "normal"}},
            "options": ["accept", "edit", "reject", "kill"],
        })]
    })
    send_card = AsyncMock(); send_skip = AsyncMock(); send_result = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card, send_skip=send_skip,
                                 send_result_request=send_result)
    await runner.on_callback(user_id=42, cb={"kind": "gate", "decision": "continue",
                                             "race_id": "R1", "slip_idx": None})
    send_card.assert_awaited_once()
    assert send_card.await_args.kwargs["payload"]["kind"] == "approval"


@pytest.mark.asyncio
async def test_on_result_positions_resumes_graph_and_sends_skip_if_terminal():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={})   # terminal, no interrupt, no skip
    send_card = AsyncMock(); send_skip = AsyncMock(); send_result = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card, send_skip=send_skip,
                                 send_result_request=send_result)
    await runner.on_result_positions(user_id=7, race_id="R1", positions={3: 1, 1: 2})
    call = graph.ainvoke.await_args
    from langgraph.types import Command
    assert isinstance(call.args[0], Command)
    # Terminal => no card or skip (nothing to say)
    send_card.assert_not_called()
    send_skip.assert_not_called()


def test_active_races_tracks_recorders():
    graph = MagicMock(); send_card = AsyncMock(); send_skip = AsyncMock(); sr = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card, send_skip=send_skip,
                                 send_result_request=sr)
    assert runner.active_races == set()
    runner._recorders["R1"] = MagicMock()
    assert runner.active_races == {"R1"}


def test_recorder_provider_returns_registered_recorder():
    graph = MagicMock(); send_card = AsyncMock(); send_skip = AsyncMock(); sr = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card, send_skip=send_skip,
                                 send_result_request=sr)
    fake_recorder = MagicMock()
    runner._recorders["R1"] = fake_recorder
    assert runner.recorder_provider("R1") is fake_recorder
    assert runner.recorder_provider("R2") is None


def test_drawdown_and_unlock_toggle():
    graph = MagicMock(); send_card = AsyncMock(); send_skip = AsyncMock(); sr = AsyncMock()
    runner = TelegramGraphRunner(graph, send_card=send_card, send_skip=send_skip,
                                 send_result_request=sr)
    assert runner.drawdown_locked is False
    runner.trip_drawdown(token="unlock-abcd1234")
    assert runner.drawdown_locked is True
    assert runner.expected_unlock_token == "unlock-abcd1234"
    runner.unlock()
    assert runner.drawdown_locked is False
