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
from services.stake.callbacks import ConfirmCB, BankrollCB
from services.stake.settings import get_stake_settings
from services.stake.bankroll.repository import BankrollRepository
from services.stake.handlers.commands import balance_header
from services.stake.keyboards.stake_kb import bankroll_confirm_kb, bankroll_input_kb
from services.stake.audit.logger import AuditLogger
from services.stake.pipeline.graph import build_analysis_graph

logger = logging.getLogger("stake")

router = Router(name="callbacks")


async def _run_analysis_pipeline(
    callback: CallbackQuery,
    state: FSMContext,
    fsm_data: dict,
    settings,
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

    # Progressive update: let user know analysis is starting
    await callback.message.answer(
        f"{header}Race confirmed. Running analysis..."
    )

    # Build initial state from stored parse results
    pipeline_result = fsm_data.get("pipeline_result", {})

    initial_state: dict = {
        "parsed_race": pipeline_result.get("parsed_race"),
        "enriched_runners": pipeline_result.get("enriched_runners") or [],
        "overround_active": pipeline_result.get("overround_active"),
        "overround_raw": pipeline_result.get("overround_raw"),
        "ambiguous_fields": pipeline_result.get("ambiguous_fields") or [],
    }

    try:
        # Send progressive updates
        await callback.message.answer(
            f"{header}Checking margins..."
        )

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
        stake_pct = repo.get_stake_pct()

        if detected_bankroll is not None:
            # BANK-02 / D-11: bankroll found in paste — ask to confirm
            # D-16: include stake % guidance in confirmation message
            await state.set_state(PipelineStates.awaiting_bankroll_confirm)
            await state.update_data(detected_bankroll=detected_bankroll)
            stake_amount = detected_bankroll * stake_pct
            current_info = (
                f"Current balance: {current_balance:.2f} USDT"
                if current_balance is not None
                else "No balance on record."
            )
            await callback.message.answer(
                f"{header}"
                f"Detected balance in paste: <b>{detected_bankroll:.2f} USDT</b>\n"
                f"{current_info}\n\n"
                f"At current stake ({stake_pct*100:.1f}%), each bet would be "
                f"~{stake_amount:.2f} USDT.\n"
                f"To adjust: /stake 3\n\n"
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
