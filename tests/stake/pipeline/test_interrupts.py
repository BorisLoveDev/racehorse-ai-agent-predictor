import pytest
from pydantic import ValidationError

from services.stake.pipeline.interrupts import (
    InterruptGatePayload, InterruptApprovalPayload, InterruptResume,
    GateDecision, ApprovalDecision,
)


def test_gate_payload_roundtrip():
    p = InterruptGatePayload(
        race_id="R1", reason="overround_high", overround=0.22,
        missing_fields=[], options=["continue", "skip", "ask"],
    )
    assert p.kind == "gate"
    d = p.model_dump(mode="json")
    assert d["options"] == ["continue", "skip", "ask"]
    assert d["kind"] == "gate"


def test_gate_payload_forbids_extra_fields():
    with pytest.raises(ValidationError):
        InterruptGatePayload(
            race_id="R1", reason="x", overround=0.1,
            options=["continue"], bogus="extra",
        )


def test_gate_payload_rejects_unknown_option():
    with pytest.raises(ValidationError):
        InterruptGatePayload(
            race_id="R1", reason="x", overround=0.1,
            options=["maybe"],
        )


def test_approval_payload_has_defaults():
    p = InterruptApprovalPayload(
        race_id="R1", bet_slip={"stake": 1.0}, rationale="x",
        options=["accept", "edit", "reject", "kill"],
    )
    assert p.kind == "approval"
    assert p.mode == "paper"
    assert p.reflection_id is None


def test_approval_payload_requires_bet_slip():
    with pytest.raises(ValidationError):
        InterruptApprovalPayload(
            race_id="R1", rationale="x",
            options=["accept", "edit", "reject", "kill"],
        )


def test_approval_payload_accepts_dry_run_and_live_modes():
    # Even live is allowed by the payload schema — the invariant check is
    # enforced elsewhere (Task 13/15). Payload is a pure data type.
    for mode in ("paper", "dry_run", "live"):
        p = InterruptApprovalPayload(
            race_id="R1", bet_slip={}, rationale="x",
            options=["accept"], mode=mode,
        )
        assert p.mode == mode


def test_resume_decision_union_typed():
    for d in ("continue", "skip", "ask", "accept", "edit", "reject", "kill"):
        r = InterruptResume(decision=d)
        assert r.decision == d


def test_resume_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        InterruptResume(decision="bogus")


def test_resume_details_optional():
    r = InterruptResume(decision="accept")
    assert r.details is None
    r2 = InterruptResume(decision="accept", details={"slip_idx": 0})
    assert r2.details == {"slip_idx": 0}


def test_resume_forbids_extra_fields():
    with pytest.raises(ValidationError):
        InterruptResume(decision="accept", slip_idx=0)


import asyncio
from unittest.mock import AsyncMock

from services.stake.pipeline.runner import run_or_resume


@pytest.mark.asyncio
async def test_run_or_resume_initial_state():
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(return_value={"ok": True})
    out = await run_or_resume(graph, thread_id="t1",
                              initial_state={"raw_input": "x"})
    assert out == {"ok": True}
    call = graph.ainvoke.await_args
    # First positional arg is the initial state
    assert call.args[0] == {"raw_input": "x"}
    # Second positional is config={"configurable": {"thread_id": "t1"}}
    cfg = call.kwargs.get("config") or (call.args[1] if len(call.args) > 1 else None)
    assert cfg == {"configurable": {"thread_id": "t1"}}


@pytest.mark.asyncio
async def test_run_or_resume_with_resume_value():
    from langgraph.types import Command
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(return_value={"ok": True})
    await run_or_resume(graph, thread_id="t1", resume_value={"decision": "skip"})
    call = graph.ainvoke.await_args
    # First positional arg should be a Command instance
    assert isinstance(call.args[0], Command)
