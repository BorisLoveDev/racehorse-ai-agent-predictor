"""
Callback handlers for inline keyboard buttons in the Stake Advisor Bot.

Handles ConfirmCB (parse confirm/reject), BankrollCB (bankroll confirm/set),
and SkipCB (high margin skip/continue) callback queries.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from services.stake.states import PipelineStates
from services.stake.callbacks import ConfirmCB, BankrollCB, SkipCB
from services.stake.settings import get_stake_settings
from services.stake.bankroll.repository import BankrollRepository
from services.stake.handlers.commands import balance_header
from services.stake.keyboards.stake_kb import bankroll_confirm_kb, bankroll_input_kb, skip_confirm_kb
from services.stake.audit.logger import AuditLogger
from services.stake.pipeline.graph import build_analysis_graph
from services.stake.handlers.pipeline import _run_analysis_inline

logger = logging.getLogger("stake")

router = Router(name="callbacks")


async def _safe_remove_buttons(callback: CallbackQuery) -> None:
    """Remove inline keyboard buttons after user clicks. Silently ignores errors."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def _safe_edit(callback: CallbackQuery, text: str, **kwargs) -> None:
    """Edit the callback message text. Falls back to answer() on error."""
    try:
        await callback.message.edit_text(text, **kwargs)
    except Exception:
        await callback.message.answer(text, **kwargs)


async def _run_analysis_pipeline(
    callback: CallbackQuery,
    state: FSMContext,
    fsm_data: dict,
    settings,
    force_continue: bool = False,
) -> None:
    """Run the Phase 2 analysis pipeline after race confirmation."""
    audit = AuditLogger()
    header = balance_header(settings.database_path)

    pipeline_result = fsm_data.get("pipeline_result", {})
    overround_active = pipeline_result.get("overround_active")

    # Check margin BEFORE running expensive pipeline
    try:
        threshold = float(settings.sizing.skip_overround_threshold)
    except (TypeError, ValueError, AttributeError):
        threshold = 15.0

    if overround_active is not None and not force_continue:
        margin_pct = (overround_active - 1.0) * 100.0
        if margin_pct > threshold:
            await state.set_state(PipelineStates.awaiting_skip_confirm)
            await _safe_edit(
                callback,
                f"<b>High margin: {margin_pct:.1f}%</b>\n\n"
                f"Bookmaker margin ({margin_pct:.1f}%) exceeds {threshold:.0f}% threshold. "
                f"The book is heavily squeezed — finding +EV bets is unlikely.\n\n"
                f"Continuing will cost API credits with low chance of profit.",
                parse_mode="HTML",
                reply_markup=skip_confirm_kb(),
            )
            return

    # Run analysis via shared helper
    await _run_analysis_inline(
        callback.message, state, pipeline_result, header, audit, force_continue
    )


@router.callback_query(ConfirmCB.filter())
async def handle_parse_confirm(
    callback: CallbackQuery,
    callback_data: ConfirmCB,
    state: FSMContext,
) -> None:
    """Handle parse confirmation inline buttons."""
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    await callback.answer()
    await _safe_remove_buttons(callback)

    if callback_data.action == "no":
        await state.set_state(PipelineStates.idle)
        audit.log_entry("user_rejected", {})
        await callback.message.answer("Parse rejected. Paste new race data when ready.")
        return

    if callback_data.action == "yes":
        audit.log_entry("user_confirmed", {})
        data = await state.get_data()

        pipeline_result = data.get("pipeline_result", {})
        detected_bankroll = pipeline_result.get("detected_bankroll")

        repo = BankrollRepository(db_path=settings.database_path)
        current_balance = repo.get_balance()

        if detected_bankroll is not None:
            await state.set_state(PipelineStates.awaiting_bankroll_confirm)
            await state.update_data(detected_bankroll=detected_bankroll)
            current_info = (
                f"Current balance: {current_balance:.2f} USDT"
                if current_balance is not None
                else "No balance on record."
            )
            await callback.message.answer(
                f"Detected balance in paste: <b>{detected_bankroll:.2f} USDT</b>\n"
                f"{current_info}\n\n"
                "Use detected balance?",
                parse_mode="HTML",
                reply_markup=bankroll_confirm_kb(),
            )

        elif current_balance is None:
            await state.set_state(PipelineStates.awaiting_bankroll_input)
            await callback.message.answer(
                "No bankroll on record.\n"
                "Please enter your current USDT balance:",
                reply_markup=bankroll_input_kb(),
            )

        else:
            await _run_analysis_pipeline(callback, state, data, settings)


@router.callback_query(BankrollCB.filter())
async def handle_bankroll_action(
    callback: CallbackQuery,
    callback_data: BankrollCB,
    state: FSMContext,
) -> None:
    """Handle bankroll confirmation inline buttons."""
    settings = get_stake_settings()
    audit = AuditLogger()

    await callback.answer()
    await _safe_remove_buttons(callback)

    if callback_data.action == "no":
        await state.set_state(PipelineStates.idle)
        await callback.message.answer("Cancelled. Paste new race data when ready.")
        return

    if callback_data.action == "yes":
        data = await state.get_data()
        detected = data.get("detected_bankroll")
        repo = BankrollRepository(db_path=settings.database_path)
        if detected is not None:
            repo.set_balance(detected)
            audit.log_entry("bankroll_set", {"balance": detected, "source": "paste_detected"})
        await _run_analysis_pipeline(callback, state, data, settings)

    if callback_data.action == "keep":
        data = await state.get_data()
        audit.log_entry("bankroll_kept", {"source": "user_kept_current"})
        await _run_analysis_pipeline(callback, state, data, settings)

    if callback_data.action == "set":
        await state.set_state(PipelineStates.awaiting_bankroll_input)
        await callback.message.answer(
            "Enter your current USDT balance:",
            reply_markup=bankroll_input_kb(),
        )


@router.callback_query(SkipCB.filter())
async def handle_skip_decision(
    callback: CallbackQuery,
    callback_data: SkipCB,
    state: FSMContext,
) -> None:
    """Handle user's decision on high-margin skip."""
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    await callback.answer()
    await _safe_remove_buttons(callback)

    if callback_data.action == "skip":
        await state.set_state(PipelineStates.idle)
        audit.log_entry("user_skipped_high_margin", {})
        await callback.message.answer("Race skipped. Paste new race data when ready.")
        return

    if callback_data.action == "continue":
        audit.log_entry("user_forced_continue_high_margin", {})
        data = await state.get_data()
        pipeline_result = data.get("pipeline_result", {})
        await _run_analysis_inline(
            callback.message, state, pipeline_result, header, audit, force_continue=True
        )
