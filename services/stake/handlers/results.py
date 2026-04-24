"""
Result submission and evaluation handlers for the Stake Advisor Bot.

Handles the full result flow:
    TrackingCB (placed/tracked) -> awaiting_result
    -> result text -> parse -> [low confidence: clarification | high confidence: confirm]
    -> ResultCB confirm -> evaluate -> P&L display -> bankroll update
    -> DrawdownCB unlock -> drawdown protection removed

Also handles /unlock_drawdown via DrawdownCB and the command handler in commands.py.
"""

import html
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from services.stake.states import PipelineStates
from services.stake.callbacks import TrackingCB, ResultCB, DrawdownCB
from services.stake.settings import get_stake_settings
from services.stake.handlers.commands import balance_header
from services.stake.results.parser import ResultParser
from services.stake.results.evaluator import evaluate_bets
from services.stake.results.models import ParsedResult
from services.stake.results.repository import BetOutcomesRepository
from services.stake.bankroll.repository import BankrollRepository
from services.stake.keyboards.stake_kb import result_confirm_kb, drawdown_unlock_kb
from services.stake.audit.logger import AuditLogger

logger = logging.getLogger("stake")
router = Router(name="results")


@router.callback_query(TrackingCB.filter())
async def handle_tracking_choice(
    callback: CallbackQuery,
    callback_data: TrackingCB,
    state: FSMContext,
) -> None:
    """Handle Placed / Tracked / Report-Only / Skip-Result keyboard taps.

    Actions:
        placed       — user bet the recommendation; P&L will be tracked.
        tracked      — recommendation was shown but not bet.
        report_only  — no bet was recommended (No +EV card); user still
                       wants to share the result for calibration.
        skip_result  — dismiss and go idle.

    All except skip_result transition FSM to awaiting_result so the next
    text message is parsed as race result.
    """
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    action = callback_data.action

    if action == "skip_result":
        await state.set_state(PipelineStates.idle)
        await callback.message.answer(
            "OK, skipping result. Paste a new race when ready."
        )
        return

    is_placed = action == "placed"
    await state.update_data(is_placed=is_placed)
    await state.set_state(PipelineStates.awaiting_result)

    if action == "report_only":
        label = "TRACKED (no bet)"
        prompt = (
            f"Marked as <b>{label}</b>.\n\n"
            "When the race finishes, paste the finishing order.\n"
            "Examples: <code>3,5,11,12</code>, <code>1 3 5 2 4</code>, "
            "or <code>Результат 1 3 5</code>"
        )
    else:
        label = "PLACED" if is_placed else "TRACKED"
        prompt = (
            f"Marked as <b>{label}</b>.\n\n"
            "When the race finishes, paste the result here.\n"
            "Examples: <code>3,5,11,12</code> or <code>Thunder won</code>"
        )

    await callback.message.answer(prompt, parse_mode="HTML")


@router.message(PipelineStates.awaiting_result, F.text)
async def handle_result_text(message: Message, state: FSMContext) -> None:
    """Handle result text pasted in awaiting_result state.

    Parses the result via LLM. Low-confidence results trigger clarification;
    high-confidence results proceed to confirmation.
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    raw_text = (message.text or "").strip()

    if raw_text.startswith("/"):
        return  # Let command handlers take it

    await message.answer(f"{header}Parsing result...")

    try:
        parser = ResultParser(settings)
        parsed = await parser.parse(raw_text)
    except Exception as e:
        logger.exception("Result parse error: %s", e)
        await message.answer(
            f"{header}Could not parse result: {html.escape(str(e))}\nPlease try again."
        )
        return

    # Store parsed result as dict for Redis FSM (Pydantic models not JSON-serializable)
    await state.update_data(parsed_result=parsed.model_dump())

    if parsed.confidence == "low":
        await state.set_state(PipelineStates.awaiting_result_clarification)
        order_display = parsed.finishing_order or parsed.finishing_names
        await message.answer(
            f"{header}Result seems ambiguous. Parsed as:\n"
            f"Order: {order_display}\n"
            f"Partial: {parsed.is_partial}\n\n"
            "Please clarify or re-enter the result:",
        )
        return

    # High confidence — show confirmation keyboard
    await state.set_state(PipelineStates.confirming_result)
    order_display = parsed.finishing_order or parsed.finishing_names
    partial_note = " (partial — only winner)" if parsed.is_partial else ""
    await message.answer(
        f"{header}<b>Result parsed{partial_note}:</b>\n"
        f"Finishing order: {order_display}\n\n"
        "Confirm this result?",
        parse_mode="HTML",
        reply_markup=result_confirm_kb(),
    )


@router.message(PipelineStates.awaiting_result_clarification, F.text)
async def handle_result_clarification(message: Message, state: FSMContext) -> None:
    """Re-parse with clarified text in awaiting_result_clarification state.

    Simply resets to awaiting_result and calls handle_result_text again
    with the new/clarified input.
    """
    raw_text = (message.text or "").strip()
    if raw_text.startswith("/"):
        return
    # Reset state so handle_result_text filter matches
    await state.set_state(PipelineStates.awaiting_result)
    await handle_result_text(message, state)


@router.callback_query(ResultCB.filter())
async def handle_result_confirm(
    callback: CallbackQuery,
    callback_data: ResultCB,
    state: FSMContext,
) -> None:
    """Handle result confirmation (yes/no) callback.

    On "no": resets to awaiting_result so user can re-enter.
    On "yes": evaluates bets, updates bankroll (if placed), shows P&L.
    """
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if callback_data.action == "no":
        await state.set_state(PipelineStates.awaiting_result)
        await callback.message.answer("Re-enter the result:")
        return

    # action == "yes" — evaluate bets
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()
    data = await state.get_data()

    parsed_dict = data.get("parsed_result", {})
    parsed = ParsedResult.model_validate(parsed_dict)
    final_bets = data.get("final_bets", [])
    is_placed = data.get("is_placed", False)
    run_id = data.get("run_id", 0)

    if not final_bets:
        await state.set_state(PipelineStates.idle)
        await callback.message.answer(
            f"{header}No bets to evaluate. Paste new race data when ready."
        )
        return

    # Evaluate bets (ARCH-01: pure Python — no LLM calls)
    outcomes = evaluate_bets(final_bets, parsed)

    # Persist outcomes
    repo = BetOutcomesRepository(db_path=settings.database_path)
    repo.save_outcomes(run_id, is_placed, [o.model_dump() for o in outcomes])

    # Update bankroll only when bets were actually placed
    if is_placed:
        bankroll_repo = BankrollRepository(db_path=settings.database_path)
        total_profit = sum(o.profit_usdt for o in outcomes if o.evaluable)
        current = bankroll_repo.get_balance() or 0.0
        new_balance = current + total_profit
        bankroll_repo.set_balance(new_balance)
        # Auto-reset drawdown unlock when balance recovers above threshold
        bankroll_repo.check_and_auto_reset_drawdown(
            threshold_pct=settings.risk.drawdown_threshold_pct
        )

    # Format P&L summary
    evaluable_outcomes = [o for o in outcomes if o.evaluable]
    total_profit = sum(o.profit_usdt for o in evaluable_outcomes)
    wins = sum(1 for o in evaluable_outcomes if o.won)
    losses = sum(1 for o in evaluable_outcomes if not o.won)
    non_evaluable = [o for o in outcomes if not o.evaluable]

    lines = [f"{header}<b>Result Evaluation:</b>"]
    for o in evaluable_outcomes:
        icon = "+" if o.won else "-"
        lines.append(
            f"  {icon} #{o.runner_number} {html.escape(o.runner_name)} "
            f"({o.bet_type}): {o.profit_usdt:+.2f} USDT"
        )
    if non_evaluable:
        lines.append(f"\n  {len(non_evaluable)} bet(s) not evaluable (partial result)")
    lines.append(f"\n<b>Total: {total_profit:+.2f} USDT</b> ({wins}W / {losses}L)")

    placed_label = "PLACED" if is_placed else "TRACKED"
    lines.append(f"Status: {placed_label}")

    audit.log_entry("result_evaluated", {
        "run_id": run_id,
        "is_placed": is_placed,
        "total_profit": total_profit,
        "wins": wins,
        "losses": losses,
        "outcomes": [o.model_dump() for o in outcomes],
        "finishing_order": parsed.finishing_order,
        "is_partial": parsed.is_partial,
    })

    await state.set_state(PipelineStates.idle)

    await callback.message.answer("\n".join(lines), parse_mode="HTML")

    # Run reflection + lesson extraction (non-blocking -- don't fail the flow if LLM errors)
    try:
        from services.stake.reflection.writer import ReflectionWriter
        from services.stake.reflection.extractor import LessonExtractor
        import html as html_lib

        writer = ReflectionWriter(settings)
        reflection_text = await writer.write_reflection(
            outcomes=[o.model_dump() for o in outcomes],
            final_bets=final_bets,
            parsed_result=parsed.model_dump(),
        )

        extractor = LessonExtractor(settings)
        lesson = await extractor.extract_and_save(
            reflection_text=reflection_text,
            db_path=settings.database_path,
        )

        audit.log_entry("reflection_complete", {
            "run_id": run_id,
            "reflection_length": len(reflection_text),
            "lesson_error_tag": lesson.error_tag,
            "lesson_rule": lesson.rule_sentence,
            "lesson_is_failure": lesson.is_failure_mode,
        })

        await callback.message.answer(
            f"<b>Lesson learned:</b>\n"
            f"[{html_lib.escape(lesson.error_tag)}] {html_lib.escape(lesson.rule_sentence)}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Reflection/lesson extraction failed: %s", e)
        audit.log_entry("reflection_error", {"run_id": run_id, "error": str(e)})
        # Non-fatal -- continue to idle state

    await callback.message.answer("Paste new race data when ready.")


@router.callback_query(DrawdownCB.filter())
async def handle_drawdown_unlock(
    callback: CallbackQuery,
    callback_data: DrawdownCB,
    state: FSMContext,
) -> None:
    """Handle drawdown unlock button press.

    Sets drawdown_unlocked=True in SQLite so the next analysis run
    will not be blocked by the drawdown circuit breaker.
    """
    await callback.answer()
    settings = get_stake_settings()
    repo = BankrollRepository(db_path=settings.database_path)
    repo.set_drawdown_unlocked(True)
    audit = AuditLogger()
    audit.log_entry("drawdown_unlocked", {"source": "callback"})
    await callback.message.answer(
        "Drawdown protection UNLOCKED. Recommendations will resume.\n"
        "Protection will re-activate automatically if balance drops again.\n"
        "Paste new race data when ready."
    )
