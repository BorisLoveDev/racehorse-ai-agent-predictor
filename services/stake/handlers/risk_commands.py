"""Risk commands — /kill and /resume.

Anti-tilt design:
  - /kill: hard stop for all active races (button-free because this triggers
    in panic; a single typed command is unambiguous).
  - /resume: unlocks drawdown breaker. Requires the EXPLICIT token printed
    when the breaker tripped. No button is offered: button taps happen on
    emotion, a typed token requires deliberation.
"""

DRAWDOWN_UNLOCK_TOKEN_PREFIX = "unlock-"


async def handle_kill(msg, *, runner) -> None:
    races = list(getattr(runner, "active_races", []))
    for race_id in races:
        await runner.cancel_race(race_id)
    count = len(races)
    await msg.answer(
        f"🛑 Kill switch — {count} active race(s) cancelled."
        if count else "🛑 Kill switch — nothing active to cancel."
    )


async def handle_resume(msg, *, runner) -> None:
    if not getattr(runner, "drawdown_locked", False):
        await msg.answer("Not locked — nothing to resume.")
        return
    parts = (msg.text or "").strip().split(maxsplit=1)
    expected = getattr(runner, "expected_unlock_token", None)
    if len(parts) < 2:
        await msg.answer(
            "Drawdown lock active. Type: "
            f"<code>/resume {DRAWDOWN_UNLOCK_TOKEN_PREFIX}&lt;token&gt;</code> "
            "to confirm. Check /bankroll for the token."
        )
        return
    supplied = parts[1].strip()
    if not expected or supplied != expected:
        await msg.answer(
            "Invalid unlock token. Expected the "
            f"<code>{DRAWDOWN_UNLOCK_TOKEN_PREFIX}…</code> value printed when the "
            "breaker tripped. Check /bankroll."
        )
        return
    runner.unlock()
    await msg.answer("✅ Unlocked. Drawdown lock cleared — proceed carefully.")
