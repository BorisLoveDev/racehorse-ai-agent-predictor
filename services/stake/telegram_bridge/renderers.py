"""Pure renderers — transform interrupt payloads into Telegram (text, buttons).

All user-provided content is HTML-escaped since the bot uses parse_mode=HTML.
"""
from html import escape

from services.stake.telegram_bridge.resume_router import encode_callback


def render_gate_card(payload: dict) -> tuple[str, list[dict]]:
    race_id = payload["race_id"]
    lines = [
        f"⚠️ <b>Gate check — {escape(str(race_id))}</b>",
        f"Reason: {escape(str(payload.get('reason', '')))}",
        f"Overround: {float(payload['overround']):.2%}",
    ]
    if payload.get("missing_fields"):
        lines.append("Missing: " + ", ".join(escape(str(f)) for f in payload["missing_fields"]))
    text = "\n".join(lines)
    buttons = [
        {"text": opt.capitalize(),
         "callback_data": encode_callback(kind="gate", decision=opt, race_id=race_id)}
        for opt in payload["options"]
    ]
    return text, buttons


def render_approval_card(payload: dict, slip_idx: int = 0) -> tuple[str, list[dict]]:
    slip = payload["bet_slip"]
    intent = slip["intent"]
    mode_label = f"[{payload['mode'].upper()}]"
    sel = ",".join(str(s) for s in intent["selections"])
    divisor = int(round(1.0 / float(slip["sizing_params"]["kelly_fraction"])))
    lines = [
        f"🎯 <b>Bet approval {mode_label} — {escape(str(payload['race_id']))}</b>",
        f"{escape(str(intent['market']))} #{escape(sel)}  conf={float(intent['confidence']):.2f}",
        f"Stake: {float(slip['stake']):.2f}  (Kelly/{divisor})",
        (f"EV: {float(slip['expected_value']):+.2f}  "
         f"max_loss: {float(slip['max_loss']):.2f}  "
         f"profit_if_win: {float(slip['profit_if_win']):.2f}  "
         f"VaR95: {float(slip['portfolio_var_95']):.2f}"),
        f"Rationale: {escape(str(payload.get('rationale') or ''))}",
    ]
    if slip.get("caps_applied"):
        lines.append("Caps: " + ", ".join(escape(str(c)) for c in slip["caps_applied"]))
    text = "\n".join(lines)
    buttons = [
        {"text": opt.capitalize(),
         "callback_data": encode_callback(
             kind="approval", decision=opt, race_id=payload["race_id"], slip_idx=slip_idx,
         )}
        for opt in payload["options"]
    ]
    return text, buttons


def render_skip_card(*, race_id: str, reason: str) -> str:
    return f"⏭️ <b>Skip — {escape(str(race_id))}</b>\n{escape(str(reason))}"


def render_result_request(race_id: str) -> str:
    return (
        f"🏁 <b>Race {escape(str(race_id))} — results?</b>\n"
        f"Reply with finishing positions, one per line:\n"
        f"<code>3:1\n1:2\n5:3</code>"
    )
