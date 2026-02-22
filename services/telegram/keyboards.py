"""
Reusable inline keyboard builder functions for the Telegram bot.
"""

from typing import Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.telegram.callbacks import MenuCB, RaceCB, StatsCB, ControlCB, DigestCB

RACES_PER_PAGE = 5


def main_menu_kb(bot_enabled: bool = True, bot_mode: str = "auto") -> InlineKeyboardMarkup:
    """Main menu keyboard — 2x3 grid."""
    pause_label = "▶ Resume Bot" if not bot_enabled else "⏸ Pause Bot"
    mode_label = f"Mode: {'AUTO' if bot_mode == 'auto' else 'MANUAL'}"

    builder = InlineKeyboardBuilder()
    builder.button(text="🏇 Browse Races", callback_data=MenuCB(action="races"))
    builder.button(text="📊 Active Bets", callback_data=MenuCB(action="status"))
    builder.button(text="📜 History", callback_data=MenuCB(action="history"))
    builder.button(text="📈 Statistics", callback_data=MenuCB(action="stats"))
    builder.button(text=pause_label, callback_data=ControlCB(action="toggle"))
    builder.button(text=mode_label, callback_data=ControlCB(action="mode"))
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def race_list_kb(
    races: list,
    page: int = 0,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """Race list keyboard with pagination."""
    builder = InlineKeyboardBuilder()

    # Race buttons (one per row for clarity)
    start = page * RACES_PER_PAGE
    end = start + RACES_PER_PAGE
    page_races = races[start:end]

    for i, race in enumerate(page_races):
        global_idx = start + i
        label = f"{race.location} R{race.race_number}"
        builder.button(
            text=label,
            callback_data=RaceCB(action="detail", idx=global_idx, pg=page)
        )

    builder.adjust(1)  # One button per row

    # Pagination row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀ Prev",
                callback_data=RaceCB(action="list", idx=0, pg=page - 1).pack()
            )
        )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="Next ▶",
                callback_data=RaceCB(action="list", idx=0, pg=page + 1).pack()
            )
        )

    # Menu button
    menu_button = InlineKeyboardButton(
        text="<< Menu",
        callback_data=MenuCB(action="back").pack()
    )

    keyboard = builder.as_markup()

    # Append nav row if needed
    if nav_buttons:
        keyboard.inline_keyboard.append(nav_buttons)
    keyboard.inline_keyboard.append([menu_button])

    return keyboard


def race_detail_kb(idx: int, pg: int = 0) -> InlineKeyboardMarkup:
    """Race detail keyboard with Analyze + Back buttons."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🤖 Analyze This Race",
        callback_data=RaceCB(action="analyze", idx=idx, pg=pg)
    )
    builder.button(
        text="<< Back to Races",
        callback_data=RaceCB(action="list", idx=0, pg=pg)
    )
    builder.adjust(1)
    return builder.as_markup()


def stats_period_kb(current: str = "all") -> InlineKeyboardMarkup:
    """Period selector for stats."""
    periods = [
        ("All Time", "all"),
        ("Today", "today"),
        ("3 Days", "3d"),
        ("Week", "week"),
    ]
    builder = InlineKeyboardBuilder()
    for label, period in periods:
        prefix = "• " if period == current else ""
        builder.button(
            text=f"{prefix}{label}",
            callback_data=StatsCB(period=period)
        )
    builder.adjust(4)
    return builder.as_markup()


def back_kb(target: str = "races", pg: int = 0) -> InlineKeyboardMarkup:
    """Generic back button."""
    builder = InlineKeyboardBuilder()
    if target == "menu":
        builder.button(text="<< Menu", callback_data=MenuCB(action="back"))
    else:
        builder.button(
            text="<< Back to Races",
            callback_data=RaceCB(action="list", idx=0, pg=pg)
        )
    return builder.as_markup()


def race_select_kb(races: list) -> InlineKeyboardMarkup:
    """Keyboard for selecting races from a digest message (manual mode).
    Uses DigestCB (prefix 'd') to avoid ambiguity with RaceCB analyze action.
    """
    builder = InlineKeyboardBuilder()
    for i, race in enumerate(races[:10]):
        label = f"{race['location']} R{race['race_number']} ({race.get('time', '?')})"
        builder.button(
            text=label,
            callback_data=DigestCB(idx=i)
        )
    builder.adjust(1)
    return builder.as_markup()
