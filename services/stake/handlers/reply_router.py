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


# Filter chain:
#   F.reply_to_message — only match when this message IS a reply
#   .from_user.is_bot  — only when the replied-to message was authored by a bot
# Combined, the handler only enters for replies to OUR recommendation cards
# (or any bot messages). Non-bot replies (user quoting their own paste,
# forwarding, etc.) do NOT match the filter and naturally fall through to
# the next router in the chain — critical because aiogram 3 consumes an
# update as soon as a handler is invoked.
@router.message(F.reply_to_message.from_user.is_bot)
async def handle_reply(message: Message, state: FSMContext) -> None:
    """Replies to bot messages → result-reporting flow for that run.

    The filter guarantees `reply_to_message` and `from_user.is_bot` are
    truthy. Inside the handler we verify DB linkage; if we can't bind the
    reply to a known pipeline run we tell the user explicitly so they know
    their reply wasn't silently eaten.
    """
    replied = message.reply_to_message
    assert replied is not None  # filter guarantees this

    settings = get_stake_settings()
    db_path = settings.database_path
    replied_text = replied.text or replied.caption or ""

    run_info = _lookup_run_by_message_id(db_path, replied.message_id)

    # If we can't map the reply to a pipeline run, tell the user clearly.
    # We MUST answer here — returning silently would consume the update in
    # aiogram 3 and the user would see no response at all.
    if run_info is None:
        if _looks_like_bot_card(replied_text):
            await message.answer(
                "⚠️ Couldn't find the original race for this reply.\n"
                "It may predate the reply-routing feature. Paste the race "
                "again as a NEW message (not a reply) to re-analyse."
            )
        else:
            await message.answer(
                "ℹ️ I can only accept race results as replies to a race "
                "recommendation card. To analyse a new race, send the paste "
                "as a new (non-reply) message."
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
