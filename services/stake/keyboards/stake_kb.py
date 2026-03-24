"""
Inline keyboard builder functions for the Stake Advisor Bot.

Follows the same pattern as services/telegram/keyboards.py using
InlineKeyboardBuilder from aiogram.
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.stake.callbacks import ConfirmCB, BankrollCB, MenuCB


def confirm_parse_kb() -> InlineKeyboardMarkup:
    """Confirm/reject parsed race summary keyboard.

    Shown after LLM parsing to let user verify extracted race data.
    Per D-22.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirm", callback_data=ConfirmCB(action="yes"))
    builder.button(text="Cancel", callback_data=ConfirmCB(action="no"))
    builder.adjust(2)
    return builder.as_markup()


def bankroll_confirm_kb() -> InlineKeyboardMarkup:
    """Confirm detected bankroll or set a different amount.

    Shown when a balance amount is detected in the pasted race text.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirm", callback_data=BankrollCB(action="yes"))
    builder.button(text="Set Different", callback_data=BankrollCB(action="set"))
    builder.button(text="Cancel", callback_data=BankrollCB(action="no"))
    builder.adjust(2, 1)
    return builder.as_markup()


def bankroll_input_kb() -> InlineKeyboardMarkup:
    """Cancel option while waiting for bankroll text input.

    Shown when user must enter balance manually (no balance detected anywhere).
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data=BankrollCB(action="no"))
    return builder.as_markup()


def main_menu_kb() -> InlineKeyboardMarkup:
    """Main menu with balance and help shortcuts.

    Per D-20: always accessible from bot responses.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Balance", callback_data=MenuCB(action="balance"))
    builder.button(text="Help", callback_data=MenuCB(action="help"))
    builder.adjust(2)
    return builder.as_markup()
