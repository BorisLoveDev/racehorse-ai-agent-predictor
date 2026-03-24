"""
Command handlers for the Stake Advisor Bot.

Implements /start, /help, /cancel, /balance, and /stake commands.
Every response includes a balance header per BANK-04 / D-14.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from services.stake.states import PipelineStates
from services.stake.bankroll.repository import BankrollRepository
from services.stake.settings import get_stake_settings
from services.stake.keyboards.stake_kb import main_menu_kb

router = Router(name="commands")


def balance_header(db_path: str) -> str:
    """Generate balance header for every response.

    Shows current balance and stake percentage, or 'Balance: not set'
    if no bankroll has been configured. Per BANK-04 / D-14.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Formatted header string with separator line.
    """
    repo = BankrollRepository(db_path=db_path)
    balance = repo.get_balance()
    stake_pct = repo.get_stake_pct()
    if balance is not None:
        return f"Balance: {balance:.2f} USDT | Stake: {stake_pct * 100:.0f}%\n{'─' * 30}\n"
    return f"Balance: not set\n{'─' * 30}\n"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start — welcome message and reset to idle state.

    Per D-19: show balance header, welcome text, command list, main menu.
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    await state.set_state(PipelineStates.idle)
    await message.answer(
        f"{header}"
        "Welcome to Stake Racing Advisor\n\n"
        "Paste raw race text from Stake.com to get started.\n"
        "Or send a .txt file with race data.\n\n"
        "Commands:\n"
        "/help — Show all features\n"
        "/balance — View or set bankroll\n"
        "/cancel — Cancel active pipeline",
        reply_markup=main_menu_kb()
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help — full feature list and usage guide.

    Per D-19: balance header, full command list, description of pipeline steps.
    """
    settings = get_stake_settings()
    header = balance_header(settings.database_path)
    await message.answer(
        f"{header}"
        "Stake Racing Advisor — Help\n\n"
        "How to use:\n"
        "1. Paste raw race text from Stake.com\n"
        "2. Or send a .txt file with race data\n"
        "3. Review the parsed race summary\n"
        "4. Confirm to proceed with analysis\n\n"
        "Commands:\n"
        "/start — Restart the bot\n"
        "/help — This help message\n"
        "/balance — View or set your USDT bankroll\n"
        "/balance 150 — Set balance to 150 USDT\n"
        "/stake 3 — Set stake to 3% of bankroll\n"
        "/cancel — Cancel active analysis pipeline\n\n"
        "The bot will parse your race data, normalize odds, "
        "show implied probabilities and overround, then ask "
        "you to confirm before proceeding to analysis.",
        reply_markup=main_menu_kb()
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Handle /cancel — cancel active pipeline, return to idle.

    Per PIPELINE-03 / D-26: clears FSM state and confirms cancellation.
    If no active pipeline, notifies user gracefully.
    """
    current = await state.get_state()
    if current is None or current == PipelineStates.idle.state:
        await message.answer("No active pipeline to cancel.")
        return
    await state.clear()
    await state.set_state(PipelineStates.idle)
    await message.answer("Pipeline cancelled. Paste new race data when ready.")


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    """Handle /balance — view current bankroll or set new amount.

    Per D-13 / BANK-05:
    - /balance        → shows current balance and stake size
    - /balance 150    → sets balance to 150 USDT
    """
    settings = get_stake_settings()
    repo = BankrollRepository(db_path=settings.database_path)
    args = message.text.strip().split() if message.text else []

    if len(args) > 1:
        try:
            new_balance = float(args[1])
            repo.set_balance(new_balance)
            await message.answer(f"Balance updated to {new_balance:.2f} USDT")
        except ValueError:
            await message.answer("Invalid amount. Usage: /balance 150")
        return

    balance = repo.get_balance()
    stake_pct = repo.get_stake_pct()
    if balance is not None:
        await message.answer(
            f"Current balance: {balance:.2f} USDT\n"
            f"Stake size: {stake_pct * 100:.0f}% ({balance * stake_pct:.2f} USDT per bet)\n\n"
            "To update: /balance 150\n"
            "To change stake %: /stake 3"
        )
    else:
        await message.answer(
            "No balance set yet.\n\n"
            "Set your USDT bankroll: /balance 150"
        )


@router.message(Command("stake"))
async def cmd_stake(message: Message) -> None:
    """Handle /stake — view or set stake percentage.

    Per D-16: stake is a percentage of bankroll per bet.
    - /stake      → shows current stake %
    - /stake 3    → sets stake to 3% (stored as 0.03)

    Validates range: 0.5% to 10% only.
    """
    settings = get_stake_settings()
    repo = BankrollRepository(db_path=settings.database_path)
    args = message.text.strip().split() if message.text else []

    if len(args) > 1:
        try:
            pct = float(args[1]) / 100.0  # User enters 3 for 3%
            if not 0.005 <= pct <= 0.10:
                await message.answer("Stake must be between 0.5% and 10%.")
                return
            repo.set_stake_pct(pct)
            await message.answer(f"Stake updated to {pct * 100:.1f}% of bankroll.")
        except ValueError:
            await message.answer("Invalid percentage. Usage: /stake 3")
        return

    stake_pct = repo.get_stake_pct()
    await message.answer(
        f"Current stake: {stake_pct * 100:.1f}% of bankroll\n"
        "To change: /stake 3 (for 3%)"
    )
