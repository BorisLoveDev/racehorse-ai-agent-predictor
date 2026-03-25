"""
Callback handlers for inline keyboard buttons in the Stake Advisor Bot.

Handles ConfirmCB (parse confirm/reject) and BankrollCB (bankroll confirm/set)
callback queries. Per PARSE-04, BANK-02, BANK-03, and D-16 (stake % guidance
in bankroll confirmation messages).

Handlers:
    handle_parse_confirm   — ConfirmCB: user confirms or rejects parsed race
    handle_bankroll_action — BankrollCB: user confirms, changes, or cancels bankroll
"""

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

router = Router(name="callbacks")


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
            # Bankroll exists in DB — pipeline complete for Phase 1
            # D-16: show stake % info in completion message
            stake_amount = current_balance * stake_pct
            await state.set_state(PipelineStates.idle)
            await callback.message.answer(
                f"{header}"
                f"Race confirmed. Stake: {stake_pct*100:.1f}% = {stake_amount:.2f} USDT per bet.\n"
                "Analysis pipeline will be available in Phase 2.\n\n"
                "Paste new race data when ready."
            )


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

        # D-16: show stake % in confirmation
        stake_pct = repo.get_stake_pct()
        balance = repo.get_balance() or 0.0
        stake_amount = balance * stake_pct

        await state.set_state(PipelineStates.idle)
        header = balance_header(settings.database_path)  # Refresh after balance update
        await callback.message.answer(
            f"{header}"
            f"Balance confirmed. Stake: {stake_pct*100:.1f}% = {stake_amount:.2f} USDT per bet.\n"
            "Race confirmed. Analysis pipeline will be available in Phase 2.\n\n"
            "Paste new race data when ready."
        )

    if callback_data.action == "set":
        header = balance_header(settings.database_path)
        await state.set_state(PipelineStates.awaiting_bankroll_input)
        await callback.message.answer(
            f"{header}"
            "Enter your current USDT balance:",
            reply_markup=bankroll_input_kb(),
        )
