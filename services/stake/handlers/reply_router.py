"""Reply-based result routing.

Mounted at the TOP of the router chain so it catches replies to bot
recommendation cards regardless of FSM state. Flow:

1. User replies to any bot recommendation card (or No-+EV card) with
   result text like "Результат 1 3 5 2 4" or "3,5,11,12" or "Thunder won".
2. We look up the original run by the replied-to message_id (persisted in
   stake_pipeline_runs.message_id by the pipeline handler).
3. If found, we treat the message as a race-result report for THAT run,
   regardless of what FSM state the user is currently in.
4. If not found (reply to an unrelated message), we fall through to the
   next router by returning without handling.

Non-reply messages are NEVER consumed by this router — they get routed to
the normal idle/paste handler elsewhere.
"""
from __future__ import annotations

import html
import logging
import sqlite3
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from services.stake.keyboards.stake_kb import result_confirm_kb
from services.stake.results.parser import ResultParser
from services.stake.settings import get_stake_settings
from services.stake.states import PipelineStates


logger = logging.getLogger("stake.reply_router")


router = Router(name="reply_router")


_CARD_MARKERS: tuple[str, ...] = (
    "Bet Recommendations",
    "No +EV bets",
    "AI Ranking",
    "Exotic Ideas",
    "SKIP",
)


def _lookup_run_by_message_id(db_path: str, message_id: int) -> Optional[dict]:
    """Return {run_id, raw_input, parsed_race_json, result_reported_at} or None."""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT run_id, raw_input, parsed_race_json, result_reported_at "
            "FROM stake_pipeline_runs WHERE message_id = ? "
            "ORDER BY run_id DESC LIMIT 1",
            (message_id,),
        )
        row = cur.fetchone()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("reply_router: lookup failed: %s", exc)
        return None
    if not row:
        return None
    return {
        "run_id": row[0],
        "raw_input": row[1],
        "parsed_race_json": row[2],
        "result_reported_at": row[3],
    }


def _mark_run_result(db_path: str, run_id: int, positions_text: str) -> None:
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE stake_pipeline_runs "
            "SET result_positions = ?, result_reported_at = datetime('now') "
            "WHERE run_id = ?",
            (positions_text, run_id),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as exc:
        logger.warning("reply_router: mark result failed: %s", exc)


def _looks_like_bot_card(text: Optional[str]) -> bool:
    """Heuristic: replied-to message contains a recommendation-card marker.

    Cheap sanity check so we don't hijack replies to unrelated bot messages
    (e.g. settings prompts). Safe to over-match — the real gate is the
    message_id lookup in stake_pipeline_runs.
    """
    if not text:
        return False
    return any(marker in text for marker in _CARD_MARKERS)


@router.message(F.reply_to_message)
async def handle_reply(message: Message, state: FSMContext) -> None:
    """Catch replies to recommendation cards and treat them as result reports.

    Non-reply messages don't match this filter; they continue down the router
    chain unchanged.
    """
    replied = message.reply_to_message
    if replied is None:
        return
    # Only act on replies to OUR own messages. Users can reply to their own
    # paste or any third party; those must fall through.
    replied_from_bot = bool(
        getattr(replied.from_user, "is_bot", False)
        if replied.from_user is not None else False
    )
    if not replied_from_bot:
        return

    settings = get_stake_settings()
    db_path = settings.database_path
    replied_text = replied.text or replied.caption or ""

    # Short-circuit: replied-to message doesn't look like a recommendation card.
    # Still try DB lookup — a card may not match markers if it was a skip card
    # with unusual wording — but skip if clearly not ours.
    run_info = _lookup_run_by_message_id(db_path, replied.message_id)
    if run_info is None and not _looks_like_bot_card(replied_text):
        return  # genuinely not ours — fall through

    if run_info is None:
        # Replied to a bot card we don't recognise (pre-hotfix runs, or a
        # non-pipeline message). Tell the user we can't bind it.
        await message.answer(
            "⚠️ Couldn't find the original race for this reply.\n"
            "Paste the race text again as a new message to re-analyse."
        )
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        return

    # Prevent double-submit: if the run already has a result, confirm overwrite.
    if run_info.get("result_reported_at"):
        await message.answer(
            "ℹ️ You've already submitted a result for this race. "
            "The new value will replace the old one."
        )

    # Processing indicator — user asked explicitly for visible progress.
    status_msg = await message.answer("⏳ Parsing result…")

    try:
        parser = ResultParser(settings=settings)
        parsed = await parser.parse(raw_text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("reply_router: result parse failed")
        try:
            await status_msg.edit_text(
                f"Could not parse result: {html.escape(str(exc))}"
            )
        except Exception:
            pass
        return

    _mark_run_result(db_path, run_info["run_id"], raw_text)

    # Surface parsed shape back to user so they can confirm. We deliberately
    # don't auto-evaluate bets here — the existing confirm flow already does
    # that when user taps Confirm. For no-bet runs the result is still
    # persisted above for calibration.
    await state.update_data(
        run_id=run_info["run_id"],
        is_placed=False,
        parsed_result=parsed.model_dump(),
    )
    await state.set_state(PipelineStates.confirming_result)

    positions: list[str] = []
    if parsed.finishing_order:
        positions = [str(n) for n in parsed.finishing_order]
    elif parsed.finishing_names:
        positions = list(parsed.finishing_names)

    summary = ", ".join(positions) if positions else html.escape(raw_text)
    try:
        await status_msg.edit_text(
            f"Result parsed: <b>{html.escape(summary)}</b>\n\n"
            f"Confirm to save for calibration?",
            parse_mode="HTML",
            reply_markup=result_confirm_kb(),
        )
    except Exception:
        await message.answer(
            f"Result parsed: <b>{html.escape(summary)}</b>\n\n"
            f"Confirm to save for calibration?",
            parse_mode="HTML",
            reply_markup=result_confirm_kb(),
        )
