"""
Inline keyboard builder functions for the Stake Advisor Bot.

Follows the same pattern as services/telegram/keyboards.py using
InlineKeyboardBuilder from aiogram.
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.stake.callbacks import ConfirmCB, BankrollCB, MenuCB, SkipCB, TrackingCB, ResultCB, DrawdownCB


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
    """Confirm detected bankroll, keep current, or set different.

    Shown when a balance amount is detected in the pasted race text.
    Three options: use detected, keep current balance, or enter manually.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Use Detected", callback_data=BankrollCB(action="yes"))
    builder.button(text="Keep Current", callback_data=BankrollCB(action="keep"))
    builder.button(text="Set Different", callback_data=BankrollCB(action="set"))
    builder.adjust(2, 1)
    return builder.as_markup()


def bankroll_input_kb() -> InlineKeyboardMarkup:
    """Cancel option while waiting for bankroll text input.

    Shown when user must enter balance manually (no balance detected anywhere).
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Cancel", callback_data=BankrollCB(action="no"))
    return builder.as_markup()


def skip_confirm_kb() -> InlineKeyboardMarkup:
    """Continue or skip when bookmaker margin is too high.

    Shown when pre-analysis check detects high overround.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Continue Anyway", callback_data=SkipCB(action="continue"))
    builder.button(text="Skip Race", callback_data=SkipCB(action="skip"))
    builder.adjust(2)
    return builder.as_markup()


def tracking_kb() -> InlineKeyboardMarkup:
    """Placed/Tracked choice shown on recommendation message. Per D-03.

    After a recommendation is shown, ask whether the user placed the bets
    (for P&L tracking) or is only tracking for analysis purposes.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Placed (I bet this)", callback_data=TrackingCB(action="placed"))
    builder.button(text="Tracked (not bet)", callback_data=TrackingCB(action="tracked"))
    builder.adjust(2)
    return builder.as_markup()


def result_confirm_kb() -> InlineKeyboardMarkup:
    """Confirm/reject parsed result keyboard shown before P&L evaluation."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirm", callback_data=ResultCB(action="yes"))
    builder.button(text="Re-enter", callback_data=ResultCB(action="no"))
    builder.adjust(2)
    return builder.as_markup()


def report_result_kb() -> InlineKeyboardMarkup:
    """Offer to collect race result even when no bet was placed.

    Used on 'No +EV bets' cards so the bot can still gather outcomes for
    calibration. User picks Report (paste positions) or Skip (dismiss).
    Uses TrackingCB with a new 'report_only' action so the existing results
    router can bind it without a new callback type.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Report Result", callback_data=TrackingCB(action="report_only"))
    builder.button(text="Skip", callback_data=TrackingCB(action="skip_result"))
    builder.adjust(2)
    return builder.as_markup()


def drawdown_unlock_kb() -> InlineKeyboardMarkup:
    """Unlock drawdown protection inline button."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Unlock Protection", callback_data=DrawdownCB(action="unlock"))
    builder.adjust(1)
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
