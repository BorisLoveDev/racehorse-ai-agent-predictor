"""
Callback data classes for aiogram inline keyboard interactions.

All callback strings are kept short to stay well under Telegram's 64-byte limit.
"""

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    """Main menu actions. Example: 'm:races' = 7 bytes."""
    action: str  # "races", "status", "history", "stats", "settings"


class RaceCB(CallbackData, prefix="r"):
    """Race browser actions. Example: 'r:detail:5:0' = 12 bytes."""
    action: str  # "list", "detail", "analyze", "back"
    idx: int = 0  # index in cached race list
    pg: int = 0   # page number


class StatsCB(CallbackData, prefix="s"):
    """Stats period selector. Example: 's:week' = 6 bytes."""
    period: str  # "all", "today", "3d", "week"


class DigestCB(CallbackData, prefix="d"):
    """Manual-mode digest race selection. Example: 'd:3' = 3 bytes."""
    idx: int = 0  # index in digest race list


class ControlCB(CallbackData, prefix="c"):
    """Bot control actions. Example: 'c:toggle' = 8 bytes."""
    action: str  # "toggle", "mode", "back"
