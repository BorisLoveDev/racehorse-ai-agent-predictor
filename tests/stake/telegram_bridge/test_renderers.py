import pytest
from services.stake.telegram_bridge.renderers import (
    render_gate_card, render_approval_card, render_skip_card, render_result_request,
)


def _approval_payload(stake: float = 2.0, mode: str = "paper"):
    return {
        "kind": "approval", "race_id": "R1", "mode": mode,
        "rationale": "phase1_auto_accept", "reflection_id": None,
        "bet_slip": {
            "intent": {"market": "win", "selections": [3], "confidence": 0.6,
                       "rationale_id": "r", "edge_source": "paper_only"},
            "stake": stake, "kelly_fraction_used": 0.25,
            "expected_return": 5.0, "expected_value": 0.3,
            "max_loss": stake, "profit_if_win": stake * 1.5,
            "portfolio_var_95": stake, "caps_applied": [], "mode": mode,
            "sizing_params": {"kelly_fraction": 0.25, "risk_mode": "normal"},
        },
        "options": ["accept", "edit", "reject", "kill"],
    }


def test_gate_card_has_race_id_and_overround():
    payload = {
        "kind": "gate", "race_id": "R1", "reason": "overround_0.14",
        "overround": 0.14, "missing_fields": [],
        "options": ["continue", "skip", "ask"],
    }
    text, buttons = render_gate_card(payload)
    assert "R1" in text
    assert "14" in text or "0.14" in text
    data = [b["callback_data"] for b in buttons]
    assert any(d.startswith("sg:continue:") for d in data)
    assert any(d.startswith("sg:skip:") for d in data)
    assert any(d.startswith("sg:ask:") for d in data)
    assert len(buttons) == 3


def test_gate_card_lists_missing_fields():
    payload = {
        "kind": "gate", "race_id": "R1", "reason": "missing:distance,date",
        "overround": 0.05, "missing_fields": ["distance", "date"],
        "options": ["continue", "skip", "ask"],
    }
    text, buttons = render_gate_card(payload)
    assert "distance" in text
    assert "date" in text


def test_gate_card_hard_skip_only_one_button():
    payload = {
        "kind": "gate", "race_id": "R1", "reason": "overround_0.20_hard_skip",
        "overround": 0.20, "missing_fields": [],
        "options": ["skip"],
    }
    text, buttons = render_gate_card(payload)
    assert len(buttons) == 1
    assert buttons[0]["callback_data"].startswith("sg:skip:")


def test_approval_card_paper_label():
    text, buttons = render_approval_card(_approval_payload())
    assert "PAPER" in text.upper()


def test_approval_card_shows_stake_ev_risk_triplet():
    text, _ = render_approval_card(_approval_payload(stake=2.0))
    assert "2.00" in text   # stake
    assert "0.30" in text or "+0.30" in text  # EV
    # Risk triplet labels present in some form
    assert "loss" in text.lower() or "risk" in text.lower()


def test_approval_card_has_four_buttons():
    _, buttons = render_approval_card(_approval_payload(), slip_idx=0)
    callback_data = [b["callback_data"] for b in buttons]
    assert any(d.startswith("sa:accept:") for d in callback_data)
    assert any(d.startswith("sa:edit:") for d in callback_data)
    assert any(d.startswith("sa:reject:") for d in callback_data)
    assert any(d.startswith("sa:kill:") for d in callback_data)
    assert len(buttons) == 4


def test_approval_card_escapes_html_in_rationale():
    payload = _approval_payload()
    payload["rationale"] = "<script>alert('xss')</script>"
    text, _ = render_approval_card(payload)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_skip_card_has_race_and_reason():
    text = render_skip_card(race_id="R1", reason="overround_0.20")
    assert "R1" in text
    assert "overround" in text


def test_skip_card_escapes_html():
    text = render_skip_card(race_id="<race>", reason="<bad>")
    assert "<race>" not in text
    assert "&lt;race&gt;" in text


def test_result_request_includes_race():
    text = render_result_request(race_id="R1")
    assert "R1" in text
