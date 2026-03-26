"""
Callback handlers for inline keyboard buttons in the Stake Advisor Bot.

Handles ConfirmCB (parse confirm/reject) and BankrollCB (bankroll confirm/set)
callback queries. Per PARSE-04, BANK-02, BANK-03, and D-16 (stake % guidance
in bankroll confirmation messages).

Handlers:
    handle_parse_confirm   — ConfirmCB: user confirms or rejects parsed race
    handle_bankroll_action — BankrollCB: user confirms, changes, or cancels bankroll
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


async def _run_analysis_pipeline(
    callback: CallbackQuery,
    state: FSMContext,
    fsm_data: dict,
    settings,
    force_continue: bool = False,
) -> None:
    """Run the Phase 2 analysis pipeline after race confirmation.

    Builds initial state from FSM data (parse results stored by _run_parse_pipeline),
    invokes the analysis graph, and sends the recommendation or skip message to Telegram.

    Progressive status updates are sent before launching the graph to give the user
    feedback that work is happening.

    Args:
        callback: The CallbackQuery that triggered confirmation.
        state: FSM context for state management.
        fsm_data: Data dict loaded from FSM (contains pipeline_result).
        settings: StakeSettings instance.
    """
    audit = AuditLogger()
    header = balance_header(settings.database_path)

    # Build initial state from stored parse results
    pipeline_result = fsm_data.get("pipeline_result", {})
    overround_active = pipeline_result.get("overround_active")

    # Check margin BEFORE running expensive pipeline — ask user if too high
    try:
        threshold = float(settings.sizing.skip_overround_threshold)
    except (TypeError, ValueError, AttributeError):
        threshold = 15.0
    if overround_active is not None and not force_continue:
        margin_pct = (overround_active - 1.0) * 100.0
        if margin_pct > threshold:
            await state.set_state(PipelineStates.awaiting_skip_confirm)
            await callback.message.answer(
                f"{header}"
                f"<b>High margin detected: {margin_pct:.1f}%</b>\n\n"
                f"Bookmaker margin ({margin_pct:.1f}%) exceeds the {threshold:.0f}% threshold. "
                f"This means the book is heavily squeezed — finding +EV bets is unlikely.\n\n"
                f"Continuing will cost API credits for research and analysis "
                f"with low chance of finding a profitable bet.",
                parse_mode="HTML",
                reply_markup=skip_confirm_kb(),
            )
            return

    # Progressive update: let user know analysis is starting
    await callback.message.answer(
        f"{header}Running analysis..."
    )

    initial_state: dict = {
        "parsed_race": pipeline_result.get("parsed_race"),
        "enriched_runners": pipeline_result.get("enriched_runners") or [],
        "overround_active": overround_active,
        "overround_raw": pipeline_result.get("overround_raw"),
        "ambiguous_fields": pipeline_result.get("ambiguous_fields") or [],
        # If user forced continue past margin check, disable Tier 1 skip in pipeline
        "skip_signal": False if force_continue else None,
    }

    try:
        analysis_graph = build_analysis_graph()
        result = await analysis_graph.ainvoke(initial_state)

        # Extract and send recommendation text
        recommendation_text = result.get(
            "recommendation_text",
            "Analysis complete — no output generated."
        )

        await state.set_state(PipelineStates.idle)
        await callback.message.answer(
            recommendation_text,
            parse_mode="HTML",
        )

        # Audit log: record recommendation data (D-16)
        audit.log_entry("recommendation", {
            "final_bets": result.get("final_bets") or [],
            "skip_signal": result.get("skip_signal", False),
            "skip_reason": result.get("skip_reason"),
            "skip_tier": result.get("skip_tier"),
            "analysis_summary": {
                "overall_skip": (result.get("analysis_result") or {}).get("overall_skip"),
                "ai_override": (result.get("analysis_result") or {}).get("ai_override"),
                "runner_count": len((result.get("analysis_result") or {}).get("recommendations", [])),
            },
            "overround_active": pipeline_result.get("overround_active"),
        })

    except Exception as e:
        logger.exception("Analysis pipeline error: %s", e)
        await state.set_state(PipelineStates.idle)
        await callback.message.answer(
            f"{header}Analysis error: {str(e)}\n\nPaste new race data when ready."
        )
        audit.log_entry("analysis_error", {"error": str(e)})


@router.callback_query(ConfirmCB.filter())
async def handle_parse_confirm(
    callback: CallbackQuery,
    callback_data: ConfirmCB,
    state: FSMContext,
) -> None:
    """Handle parse confirmation inline buttons.

    On "yes": checks bankroll situation and routes to:
        - awaiting_bankroll_confirm  if bankroll detected in paste (BANK-02 / D-11)
        - awaiting_bankroll_input    if no bankroll anywhere (BANK-03 / D-12)
        - idle                       if bankroll already in DB

    On "no": rejects parse, returns to idle.

    Per PARSE-04 / D-22. Bankroll messages include stake % guidance per D-16.
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    await callback.answer()

    if callback_data.action == "no":
        await state.set_state(PipelineStates.idle)
        audit.log_entry("user_rejected", {})
        await callback.message.answer(
            f"{header}Parse rejected. Paste new race data when ready."
        )
        return

    if callback_data.action == "yes":
        audit.log_entry("user_confirmed", {})
        data = await state.get_data()

        # Check bankroll situation
        pipeline_result = data.get("pipeline_result", {})
        detected_bankroll = pipeline_result.get("detected_bankroll")

        repo = BankrollRepository(db_path=settings.database_path)
        current_balance = repo.get_balance()

        if detected_bankroll is not None:
            # BANK-02 / D-11: bankroll found in paste — ask to confirm
            await state.set_state(PipelineStates.awaiting_bankroll_confirm)
            await state.update_data(detected_bankroll=detected_bankroll)
            current_info = (
                f"Current balance: {current_balance:.2f} USDT"
                if current_balance is not None
                else "No balance on record."
            )
            await callback.message.answer(
                f"{header}"
                f"Detected balance in paste: <b>{detected_bankroll:.2f} USDT</b>\n"
                f"{current_info}\n\n"
                "Use detected balance?",
                reply_markup=bankroll_confirm_kb(),
            )

        elif current_balance is None:
            # BANK-03 / D-12: no bankroll anywhere — ask explicitly
            await state.set_state(PipelineStates.awaiting_bankroll_input)
            await callback.message.answer(
                f"{header}"
                "No bankroll on record.\n"
                "Please enter your current USDT balance:",
                reply_markup=bankroll_input_kb(),
            )

        else:
            # Bankroll exists in DB — trigger Phase 2 analysis pipeline
            await _run_analysis_pipeline(callback, state, data, settings)


@router.callback_query(BankrollCB.filter())
async def handle_bankroll_action(
    callback: CallbackQuery,
    callback_data: BankrollCB,
    state: FSMContext,
) -> None:
    """Handle bankroll confirmation inline buttons.

    Actions:
        "yes" — confirm detected bankroll, save to DB, return to idle
        "no"  — cancel, return to idle
        "set" — user wants to enter different amount, go to awaiting_bankroll_input

    Per BANK-02 / D-11, D-16.
    """
    settings = get_stake_settings()
    audit = AuditLogger()

    await callback.answer()

    if callback_data.action == "no":
        await state.set_state(PipelineStates.idle)
        header = balance_header(settings.database_path)
        await callback.message.answer(
            f"{header}Cancelled. Paste new race data when ready."
        )
        return

    if callback_data.action == "yes":
        data = await state.get_data()
        detected = data.get("detected_bankroll")
        repo = BankrollRepository(db_path=settings.database_path)
        if detected is not None:
            repo.set_balance(detected)
            audit.log_entry("bankroll_set", {"balance": detected, "source": "paste_detected"})

        # Trigger Phase 2 analysis pipeline now that bankroll is confirmed
        await _run_analysis_pipeline(callback, state, data, settings)

    if callback_data.action == "set":
        header = balance_header(settings.database_path)
        await state.set_state(PipelineStates.awaiting_bankroll_input)
        await callback.message.answer(
            f"{header}"
            "Enter your current USDT balance:",
            reply_markup=bankroll_input_kb(),
        )


@router.callback_query(SkipCB.filter())
async def handle_skip_decision(
    callback: CallbackQuery,
    callback_data: SkipCB,
    state: FSMContext,
) -> None:
    """Handle user's decision on high-margin skip.

    When bookmaker margin exceeds threshold, user chooses:
        "continue" — run analysis anyway (force_continue=True bypasses Tier 1 skip)
        "skip" — skip race, return to idle
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    audit = AuditLogger()

    await callback.answer()

    if callback_data.action == "skip":
        await state.set_state(PipelineStates.idle)
        audit.log_entry("user_skipped_high_margin", {})
        await callback.message.answer(
            f"{header}Race skipped. Paste new race data when ready."
        )
        return

    if callback_data.action == "continue":
        audit.log_entry("user_forced_continue_high_margin", {})
        data = await state.get_data()
        pipeline_result = data.get("pipeline_result", {})
        await _run_analysis_inline(
            callback.message, state, pipeline_result, header, audit, force_continue=True
        )
