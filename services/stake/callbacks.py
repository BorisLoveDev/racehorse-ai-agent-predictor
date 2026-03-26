"""
Callback data classes for the Stake Advisor Bot inline keyboards.

All callback strings use short prefixes to stay well under Telegram's 64-byte limit.
Per aiogram pattern from services/telegram/callbacks.py.
"""

from aiogram.filters.callback_data import CallbackData


class ConfirmCB(CallbackData, prefix="sc"):
    """Parse confirmation callback. Example: 'sc:yes' = 6 bytes.

    Used on the parse confirmation keyboard after LLM parsing.
    """

    action: str  # "yes" | "no" | "edit"


class BankrollCB(CallbackData, prefix="sb"):
    """Bankroll confirmation callback. Example: 'sb:yes' = 6 bytes.

    Used when confirming bankroll detected in paste or setting manually.
    """

    action: str  # "yes" | "no" | "set"


class SkipCB(CallbackData, prefix="ss"):
    """Skip confirmation callback. Example: 'ss:skip' = 7 bytes.

    Used when bookmaker margin is too high — user chooses to skip or continue.
    """

    action: str  # "skip" | "continue"


class MenuCB(CallbackData, prefix="sm"):
    """Main menu actions callback. Example: 'sm:help' = 7 bytes.

    Used on the main menu keyboard for navigation.
    """

    action: str  # "help" | "balance" | "cancel"
