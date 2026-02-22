"""
Telegram Notification Service

Sends notifications about predictions and results to Telegram.
Supports interactive inline keyboards for race browsing, bot control, and stats.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message, BufferedInputFile, CallbackQuery, InlineKeyboardMarkup
)
from tabtouch_parser import TabTouchParser, NextRace, RaceDetails

from src.config.settings import get_settings, get_version
from src.database.repositories import (
    PredictionRepository,
    OutcomeRepository,
    StatisticsRepository
)
from services.telegram.charts import generate_pl_chart
from services.telegram.callbacks import MenuCB, RaceCB, StatsCB, ControlCB, DigestCB
from services.telegram.keyboards import (
    main_menu_kb, race_list_kb, race_detail_kb, stats_period_kb,
    race_select_kb, RACES_PER_PAGE
)
from src.logging_config import setup_logging

# Initialize logger
logger = setup_logging("telegram")

RACE_CACHE_TTL = 120  # seconds


class TelegramNotificationService:
    """Service for sending Telegram notifications with rate limiting."""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: aioredis.Redis = None
        self.pubsub = None

        # Rate limiting (20 msg/sec for safety margin below Telegram's 30/sec limit)
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.rate_limit_delay = 1.0 / 20  # 20 messages per second
        self.last_send_time = 0.0

        # Initialize Telegram bot
        bot_token = self.settings.api_keys.telegram_bot_token.get_secret_value()
        if not bot_token:
            raise ValueError("Telegram bot token not configured")

        self.bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.chat_id = self.settings.api_keys.telegram_chat_id

        # Initialize repositories
        self.prediction_repo = PredictionRepository(
            db_path=self.settings.database.path
        )
        self.outcome_repo = OutcomeRepository(
            db_path=self.settings.database.path
        )
        self.stats_repo = StatisticsRepository(
            db_path=self.settings.database.path
        )

        # Race browser cache
        self._race_cache: list[NextRace] = []
        self._race_cache_time: float = 0.0
        self._race_detail_cache: dict[int, RaceDetails] = {}  # idx -> RaceDetails

        # Digest cache for manual-mode race selection (url -> race dict)
        self._digest_races: list[dict] = []

        # Initialize dispatcher for commands
        self.dp = Dispatcher()
        self.router = Router()
        self._setup_commands()
        self._setup_callbacks()
        self.dp.include_router(self.router)

    # ─────────────────────────────────────────────────────────────────
    # Redis helpers
    # ─────────────────────────────────────────────────────────────────

    async def _bot_enabled(self) -> bool:
        val = await self.redis_client.get("bot:enabled")
        return val != "0"

    async def _bot_mode(self) -> str:
        val = await self.redis_client.get("bot:mode")
        return val if val in ("auto", "manual") else "auto"

    # ─────────────────────────────────────────────────────────────────
    # Race browser cache
    # ─────────────────────────────────────────────────────────────────

    async def _get_races(self) -> list[NextRace]:
        """Return cached race list, refreshing if stale."""
        if time.monotonic() - self._race_cache_time > RACE_CACHE_TTL:
            async with TabTouchParser(headless=True) as parser:
                races = await parser.get_next_races(race_type="races")
            self._race_cache = races
            self._race_detail_cache.clear()
            self._race_cache_time = time.monotonic()
        return self._race_cache

    async def _get_race_detail(self, idx: int) -> Optional[RaceDetails]:
        """Return cached race detail for index, fetching if needed."""
        if idx in self._race_detail_cache:
            return self._race_detail_cache[idx]
        races = self._race_cache
        if idx >= len(races):
            return None
        race = races[idx]
        async with TabTouchParser(headless=True) as parser:
            details = await parser.get_race_details(race.url)
        if details:
            self._race_detail_cache[idx] = details
        return details

    # ─────────────────────────────────────────────────────────────────
    # Direct race analysis trigger (from Telegram, not monitor)
    # ─────────────────────────────────────────────────────────────────

    async def _trigger_race_analysis(self, idx: int) -> Optional[str]:
        """
        Fetch race details and publish directly to Redis for orchestrator.
        Returns race label string on success, None on error.
        """
        races = self._race_cache
        if idx >= len(races):
            return None

        race = races[idx]
        race_url = race.url

        # Prevent double-trigger
        already = await self.redis_client.sismember("monitor:analyzed_races", race_url)
        if already:
            return f"{race.location} R{race.race_number} (already queued)"

        try:
            details = await self._get_race_detail(idx)
            if not details or not details.runners:
                return None

            race_start_time = details.start_time_parsed or race.time_parsed
            if not race_start_time:
                return None

            race_data = {
                "race_info": {
                    "location": details.location,
                    "date": details.date,
                    "race_number": details.race_number,
                    "race_name": details.race_name,
                    "distance": details.distance,
                    "track_condition": details.track_condition,
                    "race_type": details.race_type,
                    "start_time": details.start_time,
                    "start_time_iso": race_start_time.isoformat(),
                    "url": details.url,
                },
                "runners": [
                    {
                        "number": r.number,
                        "name": r.name,
                        "form": r.form,
                        "barrier": r.barrier,
                        "weight": r.weight,
                        "jockey": r.jockey,
                        "trainer": r.trainer,
                        "rating": r.rating,
                        "fixed_win": r.fixed_win,
                        "fixed_place": r.fixed_place,
                        "tote_win": r.tote_win,
                        "tote_place": r.tote_place,
                    }
                    for r in details.runners
                ],
                "pool_totals": details.pool_totals,
            }

            ts = datetime.utcnow().isoformat()

            await self.redis_client.publish(
                "race:ready_for_analysis",
                json.dumps({"race_url": race_url, "race_data": race_data, "timestamp": ts})
            )

            # Schedule result check
            check_time = race_start_time + timedelta(
                minutes=self.settings.timing.result_wait_minutes
            )
            await self.redis_client.publish(
                "race:schedule_result_check",
                json.dumps({"race_url": race_url, "check_time": check_time.isoformat(), "timestamp": ts})
            )

            # Mark as monitored to prevent monitor double-triggering
            key = "monitor:analyzed_races"
            await self.redis_client.sadd(key, race_url)
            await self.redis_client.expire(key, 86400)

            logger.info(f"Manually triggered analysis | race={race.location} R{race.race_number}")
            return f"{race.location} R{race.race_number}"

        except Exception as e:
            logger.error(f"Error triggering race analysis: {e}", exc_info=True)
            return None

    # ─────────────────────────────────────────────────────────────────
    # Stats helper (shared by /stats and callback)
    # ─────────────────────────────────────────────────────────────────

    async def _build_stats_response(self, period: str) -> tuple[str, Optional[object]]:
        """Build stats text and optional chart buffer for a given period."""
        stats_list = self.stats_repo.get_statistics_for_period(period)
        period_display = {"all": "All Time", "today": "Today", "3d": "Last 3 Days", "week": "This Week"}
        lines = [f"<b>📊 Agent Statistics ({period_display[period]})</b>", ""]

        for stats in stats_list:
            agent_name = stats["agent_name"].capitalize()
            total_bets = stats["total_bets"]
            total_wins = stats["total_wins"]
            win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0
            profit_loss = stats["net_profit_loss"]
            lines.extend([
                f"<b>{agent_name}:</b>",
                f"  Predictions: {stats['total_predictions']}",
                f"  Bets: {total_bets} ({total_wins}W-{stats['total_losses']}L)",
                f"  Win Rate: {win_rate:.1f}%",
                f"  P/L: ${profit_loss:+.2f}",
                ""
            ])

        chart_data = self.stats_repo.get_pl_chart_data(period)
        chart_buf = generate_pl_chart(chart_data, period_display[period]) if chart_data else None
        return "\n".join(lines), chart_buf

    # ─────────────────────────────────────────────────────────────────
    # Race list / detail message formatters
    # ─────────────────────────────────────────────────────────────────

    def _format_race_list_text(self, races: list[NextRace], page: int, total_pages: int) -> str:
        start = page * RACES_PER_PAGE
        end = start + RACES_PER_PAGE
        lines = [f"<b>🏇 Upcoming Races (page {page + 1}/{total_pages})</b>", ""]
        for i, race in enumerate(races[start:end], start + 1):
            time_str = race.time_client if hasattr(race, "time_client") else "?"
            time_until = race.time_until if hasattr(race, "time_until") else ""
            lines.append(f"{i}. <b>{race.location} R{race.race_number}</b> — {time_str} ({time_until})")
        return "\n".join(lines)

    def _format_race_detail_text(self, details: RaceDetails) -> str:
        time_str = details.start_time_client if hasattr(details, "start_time_client") else details.start_time
        time_until = details.time_until if hasattr(details, "time_until") else ""
        lines = [
            f"<b>🏇 {details.location} R{details.race_number} — {details.race_name}</b>",
            f"{details.distance} | {details.track_condition} | Starts {time_str} ({time_until})",
            ""
        ]
        for r in details.runners:
            win_odds = r.fixed_win or r.tote_win
            place_odds = r.fixed_place or r.tote_place
            win_str = f"${win_odds:.2f}" if win_odds else "N/A"
            place_str = f"${place_odds:.2f}" if place_odds else "N/A"
            jockey = f" ({r.jockey})" if r.jockey else ""
            lines.append(f"#{r.number} <b>{r.name}</b>{jockey} — {win_str}/{place_str}")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────
    # Command handlers
    # ─────────────────────────────────────────────────────────────────

    def _setup_commands(self):
        """Setup command handlers."""

        @self.router.message(Command("start", "menu"))
        async def cmd_menu(message: Message):
            """Handle /start and /menu commands — show main menu."""
            logger.info(f"Received /menu from chat_id={message.chat.id}")
            enabled = await self._bot_enabled()
            mode = await self._bot_mode()
            status_line = "🟢 Running" if enabled else "🔴 Paused"
            text = (
                "<b>🏇 Racehorse Betting Agent</b>\n\n"
                f"Status: {status_line} | Mode: {mode.upper()}\n\n"
                "Choose an action:"
            )
            await message.answer(text, reply_markup=main_menu_kb(enabled, mode))

        @self.router.message(Command("help"))
        async def cmd_help(message: Message):
            """Handle /help command."""
            lines = [
                "<b>📖 Racehorse Betting Agent — Help</b>",
                "",
                "<b>Interactive Menu:</b>",
                "/menu - Main menu with inline keyboard",
                "",
                "<b>Commands:</b>",
                "/races - Browse upcoming races (inline keyboard)",
                "/status - Active bets awaiting results",
                "/history [N] - Last N results (default 5)",
                "/stats [period] - Statistics with P/L chart",
                "/evaluate - Manually check pending bets",
                "",
                "<b>Bot Control (via /menu):</b>",
                "• Pause Bot — stops scraping to save API credits",
                "• Resume Bot — resumes normal operation",
                "• Mode: AUTO — auto-analyzes all races in trigger window",
                "• Mode: MANUAL — sends race digests; you select which to analyze",
                "",
                "<b>Stats periods:</b>",
                "• all  today  3d  week",
            ]
            await message.answer("\n".join(lines))

        @self.router.message(Command("races"))
        async def cmd_races(message: Message):
            """Show upcoming races with inline keyboard."""
            if not await self._bot_enabled():
                await message.answer(
                    "⏸ Bot is paused. Resume from /menu to browse races."
                )
                return
            try:
                await message.answer("Fetching races...")
                races = await self._get_races()
                if not races:
                    await message.answer("No upcoming horse races found.")
                    return
                total_pages = max(1, (len(races) + RACES_PER_PAGE - 1) // RACES_PER_PAGE)
                text = self._format_race_list_text(races, 0, total_pages)
                await message.answer(text, reply_markup=race_list_kb(races, 0, total_pages))
            except Exception as e:
                logger.error(f"Error in /races command: {e}", exc_info=True)
                await message.answer(f"Error fetching races: {e}")

        @self.router.message(Command("status"))
        async def cmd_status(message: Message):
            """Show active bets awaiting results."""
            try:
                pending = self.stats_repo.get_pending_predictions()
                if not pending:
                    await message.answer("<b>📊 No active bets</b>\n\nAll predictions have been evaluated.")
                    return
                lines = ["<b>📊 Active Bets Awaiting Results:</b>", ""]
                for pred in pending[:10]:
                    race_time = pred.get("race_start_time", "Unknown")
                    lines.append(f"• {pred['race_location']} R{pred['race_number']}")
                    lines.append(f"  Agent: {pred['agent_name'].capitalize()}")
                    lines.append(f"  Time: {race_time}")
                    lines.append("")
                await message.answer("\n".join(lines))
            except Exception as e:
                logger.error(f"Error in /status command: {e}", exc_info=True)
                await message.answer(f"Error fetching status: {e}")

        @self.router.message(Command("history"))
        async def cmd_history(message: Message):
            """Show last N results (default 5)."""
            try:
                args = message.text.split()
                limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
                limit = min(limit, 20)
                outcomes = self.stats_repo.get_recent_outcomes(limit)
                if not outcomes:
                    await message.answer("<b>📜 No history available</b>")
                    return
                lines = [f"<b>📜 Last {len(outcomes)} Results:</b>", ""]
                for outcome in outcomes:
                    profit_loss = outcome["net_profit_loss"]
                    emoji = "✅" if profit_loss > 0 else "❌" if profit_loss < 0 else "➖"
                    lines.append(f"{emoji} <b>{outcome['race_location']} R{outcome['race_number']}</b>")
                    lines.append(f"  Agent: {outcome['agent_name'].capitalize()}")
                    lines.append(f"  P/L: ${profit_loss:+.2f}")
                    lines.append("")
                await message.answer("\n".join(lines))
            except Exception as e:
                logger.error(f"Error in /history command: {e}", exc_info=True)
                await message.answer(f"Error fetching history: {e}")

        @self.router.message(Command("stats"))
        async def cmd_stats(message: Message):
            """Show statistics with optional period filter and P/L chart."""
            try:
                args = message.text.split()
                period = args[1].lower() if len(args) > 1 else "all"
                if period not in ["all", "today", "3d", "week"]:
                    await message.answer("Usage: /stats [all|today|3d|week]")
                    return
                stats_text, chart_buf = await self._build_stats_response(period)
                kb = stats_period_kb(period)
                if chart_buf:
                    photo = BufferedInputFile(chart_buf.read(), filename="pl_chart.png")
                    await message.answer_photo(photo=photo, caption=stats_text, reply_markup=kb)
                else:
                    await message.answer(stats_text, reply_markup=kb)
            except Exception as e:
                logger.error(f"Error in /stats command: {e}", exc_info=True)
                await message.answer(f"Error fetching statistics: {e}")

        @self.router.message(Command("evaluate"))
        async def cmd_evaluate(message: Message):
            """Manually evaluate pending predictions."""
            await message.answer("🔄 Starting evaluation of pending predictions...")
            try:
                pending = self.stats_repo.get_pending_predictions()
                if not pending:
                    await message.answer("<b>✓ No pending predictions to evaluate</b>")
                    return

                races = {}
                for pred in pending:
                    url = pred["race_url"]
                    if url not in races:
                        races[url] = []
                    races[url].append(pred)

                await message.answer(f"Found {len(pending)} predictions across {len(races)} races")

                evaluated = 0
                skipped = 0

                async with TabTouchParser(headless=True) as parser:
                    for race_url, predictions in races.items():
                        try:
                            race_result = await parser.get_race_results(race_url)
                            if not race_result or not race_result.finishing_order:
                                skipped += len(predictions)
                                continue
                            for pred in predictions:
                                eval_result = await self._evaluate_prediction_for_cmd(pred, race_result)
                                if eval_result:
                                    evaluated += 1
                                else:
                                    skipped += 1
                        except Exception as e:
                            logger.error(f"Error evaluating race | url={race_url} | error={e}", exc_info=True)
                            skipped += len(predictions)

                lines = [
                    "<b>✓ Evaluation complete</b>",
                    "",
                    f"Evaluated: {evaluated}",
                    f"Skipped (no results): {skipped}"
                ]
                await message.answer("\n".join(lines))
            except Exception as e:
                logger.error(f"Error in /evaluate command: {e}", exc_info=True)
                await message.answer(f"Error during evaluation: {e}")

    # ─────────────────────────────────────────────────────────────────
    # Callback handlers (inline keyboard)
    # ─────────────────────────────────────────────────────────────────

    def _setup_callbacks(self):
        """Register callback query handlers."""

        # ── Menu callbacks ──────────────────────────────────────────

        @self.router.callback_query(MenuCB.filter(F.action == "races"))
        async def cb_menu_races(query: CallbackQuery):
            await query.answer()
            if not await self._bot_enabled():
                await query.message.edit_text(
                    "⏸ Bot is paused. Resume first to browse races.",
                    reply_markup=main_menu_kb(False, await self._bot_mode())
                )
                return
            try:
                races = await self._get_races()
                if not races:
                    await query.message.edit_text("No upcoming horse races found.",
                                                  reply_markup=main_menu_kb(True, await self._bot_mode()))
                    return
                total_pages = max(1, (len(races) + RACES_PER_PAGE - 1) // RACES_PER_PAGE)
                text = self._format_race_list_text(races, 0, total_pages)
                await query.message.edit_text(text, reply_markup=race_list_kb(races, 0, total_pages))
            except Exception as e:
                logger.error(f"Error in races callback: {e}", exc_info=True)
                await query.message.edit_text(f"Error fetching races: {e}")

        @self.router.callback_query(MenuCB.filter(F.action == "status"))
        async def cb_menu_status(query: CallbackQuery):
            await query.answer()
            try:
                pending = self.stats_repo.get_pending_predictions()
                if not pending:
                    text = "<b>📊 No active bets</b>\n\nAll predictions have been evaluated."
                else:
                    lines = ["<b>📊 Active Bets Awaiting Results:</b>", ""]
                    for pred in pending[:10]:
                        lines.append(f"• {pred['race_location']} R{pred['race_number']}")
                        lines.append(f"  Agent: {pred['agent_name'].capitalize()}")
                        lines.append("")
                    text = "\n".join(lines)
                enabled = await self._bot_enabled()
                mode = await self._bot_mode()
                await query.message.edit_text(
                    text,
                    reply_markup=main_menu_kb(enabled, mode)
                )
            except Exception as e:
                logger.error(f"Error in status callback: {e}", exc_info=True)
                await query.message.edit_text(f"Error: {e}")

        @self.router.callback_query(MenuCB.filter(F.action == "history"))
        async def cb_menu_history(query: CallbackQuery):
            await query.answer()
            try:
                outcomes = self.stats_repo.get_recent_outcomes(5)
                if not outcomes:
                    text = "<b>📜 No history available</b>"
                else:
                    lines = ["<b>📜 Last 5 Results:</b>", ""]
                    for outcome in outcomes:
                        profit_loss = outcome["net_profit_loss"]
                        emoji = "✅" if profit_loss > 0 else "❌" if profit_loss < 0 else "➖"
                        lines.append(f"{emoji} <b>{outcome['race_location']} R{outcome['race_number']}</b>")
                        lines.append(f"  P/L: ${profit_loss:+.2f}")
                        lines.append("")
                    text = "\n".join(lines)
                enabled = await self._bot_enabled()
                mode = await self._bot_mode()
                await query.message.edit_text(text, reply_markup=main_menu_kb(enabled, mode))
            except Exception as e:
                logger.error(f"Error in history callback: {e}", exc_info=True)
                await query.message.edit_text(f"Error: {e}")

        @self.router.callback_query(MenuCB.filter(F.action == "stats"))
        async def cb_menu_stats(query: CallbackQuery):
            await query.answer()
            try:
                stats_text, chart_buf = await self._build_stats_response("all")
                kb = stats_period_kb("all")
                # Always delete+send: avoids text↔photo edit incompatibility
                if chart_buf:
                    photo = BufferedInputFile(chart_buf.read(), filename="pl_chart.png")
                    await query.message.answer_photo(photo=photo, caption=stats_text, reply_markup=kb)
                else:
                    await query.message.answer(stats_text, reply_markup=kb)
                await query.message.delete()
            except Exception as e:
                logger.error(f"Error in stats callback: {e}", exc_info=True)
                await query.message.answer(f"Error: {e}")

        @self.router.callback_query(MenuCB.filter(F.action == "back"))
        async def cb_menu_back(query: CallbackQuery):
            await query.answer()
            enabled = await self._bot_enabled()
            mode = await self._bot_mode()
            status_line = "🟢 Running" if enabled else "🔴 Paused"
            text = (
                "<b>🏇 Racehorse Betting Agent</b>\n\n"
                f"Status: {status_line} | Mode: {mode.upper()}\n\n"
                "Choose an action:"
            )
            await query.message.edit_text(text, reply_markup=main_menu_kb(enabled, mode))

        # ── Race browser callbacks ───────────────────────────────────

        @self.router.callback_query(RaceCB.filter(F.action == "list"))
        async def cb_race_list(query: CallbackQuery, callback_data: RaceCB):
            await query.answer()
            try:
                races = await self._get_races()
                if not races:
                    await query.message.edit_text("No upcoming races found.")
                    return
                page = callback_data.pg
                total_pages = max(1, (len(races) + RACES_PER_PAGE - 1) // RACES_PER_PAGE)
                page = max(0, min(page, total_pages - 1))
                text = self._format_race_list_text(races, page, total_pages)
                await query.message.edit_text(text, reply_markup=race_list_kb(races, page, total_pages))
            except Exception as e:
                logger.error(f"Error in race list callback: {e}", exc_info=True)
                await query.message.edit_text(f"Error: {e}")

        @self.router.callback_query(RaceCB.filter(F.action == "detail"))
        async def cb_race_detail(query: CallbackQuery, callback_data: RaceCB):
            await query.answer("Loading race details...")
            try:
                details = await self._get_race_detail(callback_data.idx)
                if not details:
                    await query.message.edit_text("Race details not available.")
                    return
                text = self._format_race_detail_text(details)
                kb = race_detail_kb(callback_data.idx, callback_data.pg)
                await query.message.edit_text(text, reply_markup=kb)
            except Exception as e:
                logger.error(f"Error in race detail callback: {e}", exc_info=True)
                await query.message.edit_text(f"Error loading race details: {e}")

        @self.router.callback_query(RaceCB.filter(F.action == "analyze"))
        async def cb_race_analyze(query: CallbackQuery, callback_data: RaceCB):
            """Direct analysis trigger from race browser (normal mode)."""
            await query.answer("Triggering analysis...")
            if not self._race_cache:
                await query.message.edit_text("No races cached. Please browse races first.")
                return

            label = await self._trigger_race_analysis(callback_data.idx)
            if label:
                await query.message.edit_text(
                    f"✅ Analysis triggered for <b>{label}</b>.\n\n"
                    "Predictions will arrive shortly via the bot."
                )
            else:
                await query.message.edit_text(
                    "❌ Could not trigger analysis. "
                    "Race may have already started or details unavailable."
                )

        @self.router.callback_query(DigestCB.filter())
        async def cb_digest_select(query: CallbackQuery, callback_data: DigestCB):
            """Manual-mode digest: add selected race to bot:manual_races for monitor."""
            await query.answer("Selecting race...")
            if callback_data.idx >= len(self._digest_races):
                await query.message.edit_text("Race no longer available in digest.")
                return

            race_info = self._digest_races[callback_data.idx]
            url = race_info["url"]
            await self.redis_client.sadd("bot:manual_races", url)
            label = f"{race_info['location']} R{race_info['race_number']}"
            await query.message.edit_text(
                f"✅ <b>{label}</b> selected for analysis.\n\n"
                "The monitor will trigger analysis during the next poll cycle (within 60s)."
            )

        # ── Stats period callbacks ───────────────────────────────────

        @self.router.callback_query(StatsCB.filter())
        async def cb_stats_period(query: CallbackQuery, callback_data: StatsCB):
            await query.answer()
            try:
                stats_text, chart_buf = await self._build_stats_response(callback_data.period)
                kb = stats_period_kb(callback_data.period)
                # Always delete+send: avoids text↔photo edit incompatibility
                if chart_buf:
                    photo = BufferedInputFile(chart_buf.read(), filename="pl_chart.png")
                    await query.message.answer_photo(photo=photo, caption=stats_text, reply_markup=kb)
                else:
                    await query.message.answer(stats_text, reply_markup=kb)
                await query.message.delete()
            except Exception as e:
                logger.error(f"Error in stats period callback: {e}", exc_info=True)
                await query.message.answer(f"Error: {e}")

        # ── Control callbacks ────────────────────────────────────────

        @self.router.callback_query(ControlCB.filter(F.action == "toggle"))
        async def cb_control_toggle(query: CallbackQuery):
            await query.answer()
            currently_enabled = await self._bot_enabled()
            new_val = "0" if currently_enabled else "1"
            await self.redis_client.set("bot:enabled", new_val)
            enabled = new_val == "1"
            mode = await self._bot_mode()
            status = "🟢 Resumed" if enabled else "🔴 Paused"
            logger.info(f"Bot {'enabled' if enabled else 'paused'} via Telegram")
            status_line = "🟢 Running" if enabled else "🔴 Paused"
            text = (
                f"<b>🏇 Racehorse Betting Agent</b>\n\n"
                f"Status: {status_line} | Mode: {mode.upper()}\n\n"
                f"{status} — choose an action:"
            )
            await query.message.edit_text(text, reply_markup=main_menu_kb(enabled, mode))

        @self.router.callback_query(ControlCB.filter(F.action == "mode"))
        async def cb_control_mode(query: CallbackQuery):
            await query.answer()
            current_mode = await self._bot_mode()
            new_mode = "manual" if current_mode == "auto" else "auto"
            await self.redis_client.set("bot:mode", new_mode)
            enabled = await self._bot_enabled()
            status_line = "🟢 Running" if enabled else "🔴 Paused"
            text = (
                f"<b>🏇 Racehorse Betting Agent</b>\n\n"
                f"Status: {status_line} | Mode: {new_mode.upper()}\n\n"
                f"Switched to <b>{new_mode.upper()}</b> mode.\n"
                + ("In MANUAL mode, you'll receive race digests and can select which races to analyze." if new_mode == "manual"
                   else "In AUTO mode, all races in the trigger window are analyzed automatically.")
            )
            await query.message.edit_text(text, reply_markup=main_menu_kb(enabled, new_mode))
            logger.info(f"Bot mode switched to {new_mode} via Telegram")

    # ─────────────────────────────────────────────────────────────────
    # Message sending (rate-limited)
    # ─────────────────────────────────────────────────────────────────

    async def _message_worker(self):
        """Worker task for rate-limited message sending (20 msg/sec)."""
        while True:
            try:
                message_data = await self.message_queue.get()

                now = asyncio.get_event_loop().time()
                time_since_last = now - self.last_send_time
                if time_since_last < self.rate_limit_delay:
                    await asyncio.sleep(self.rate_limit_delay - time_since_last)

                text = message_data["text"]
                reply_to = message_data.get("reply_to_message_id")

                try:
                    message = await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=text,
                        reply_to_message_id=reply_to
                    )
                    message_data["result"].set_result(message.message_id)
                except Exception as e:
                    if "Too Many Requests" in str(e) or "429" in str(e):
                        logger.warning("Rate limited by Telegram, retrying after delay")
                        await asyncio.sleep(2.0)
                        await self.message_queue.put(message_data)
                    else:
                        logger.error(f"Failed to send message: {e}", exc_info=True)
                        message_data["result"].set_result(None)

                self.last_send_time = asyncio.get_event_loop().time()
                self.message_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message worker: {e}", exc_info=True)

    async def send_message(self, text: str, reply_to_message_id: int = None) -> Optional[int]:
        """Send a message to Telegram via rate-limited queue. Returns message_id or None."""
        result_future = asyncio.Future()
        message_data = {
            "text": text,
            "reply_to_message_id": reply_to_message_id,
            "result": result_future
        }
        await self.message_queue.put(message_data)
        try:
            message_id = await asyncio.wait_for(result_future, timeout=30.0)
            return message_id
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for message to send")
            return None

    # ─────────────────────────────────────────────────────────────────
    # Service lifecycle
    # ─────────────────────────────────────────────────────────────────

    async def start(self):
        """Start the Telegram service."""
        redis_settings = self.settings.redis
        self.redis_client = await aioredis.from_url(
            f"redis://{redis_settings.host}:{redis_settings.port}/{redis_settings.db}",
            password=redis_settings.password if redis_settings.password else None,
            encoding="utf-8",
            decode_responses=True
        )

        # Set default control keys if not present
        if not await self.redis_client.exists("bot:enabled"):
            await self.redis_client.set("bot:enabled", "1")
        if not await self.redis_client.exists("bot:mode"):
            await self.redis_client.set("bot:mode", "auto")

        # Subscribe to channels
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(
            "predictions:new",
            "results:evaluated",
            "races:digest"
        )

        # Start message worker for rate limiting
        asyncio.create_task(self._message_worker())

        logger.info(f"🚀 Telegram Notification Service v{get_version()} started")
        logger.info(f"Chat ID: {self.chat_id}")
        logger.info("Listening for notifications and commands (rate-limited 20 msg/sec)...")

        try:
            bot_info = await self.bot.get_me()
            logger.info(f"Bot connected | username=@{bot_info.username} | id={bot_info.id}")
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}", exc_info=True)
            return

        logger.info("Starting polling...")
        await asyncio.gather(
            self.dp.start_polling(self.bot),
            self.listen_loop()
        )

    async def listen_loop(self):
        """Listen for notification triggers."""
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    channel = message["channel"]
                    data = json.loads(message["data"])

                    if channel == "predictions:new":
                        await self.handle_new_predictions(data)
                    elif channel == "results:evaluated":
                        await self.handle_results_evaluated(data)
                    elif channel == "races:digest":
                        await self.handle_races_digest(data)

                except Exception as e:
                    logger.error(f"Error processing notification: {e}", exc_info=True)

    async def handle_races_digest(self, data: dict):
        """Handle manual-mode race digest — send race list with select buttons."""
        races = data.get("races", [])
        if not races:
            return

        # Cache for callback handler
        self._digest_races = races

        lines = [f"<b>🏇 Upcoming Races — Select to Analyze</b>", ""]
        for i, race in enumerate(races, 1):
            lines.append(f"{i}. <b>{race['location']} R{race['race_number']}</b> — {race['time']}")

        text = "\n".join(lines)
        kb = race_select_kb(races)

        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text, reply_markup=kb)
            logger.info(f"Sent manual-mode digest | races={len(races)}")
        except Exception as e:
            logger.error(f"Error sending race digest: {e}", exc_info=True)

    # ─────────────────────────────────────────────────────────────────
    # Prediction / Result notification handlers
    # ─────────────────────────────────────────────────────────────────

    async def handle_new_predictions(self, data: dict):
        """Handle new prediction notification."""
        race_url = data["race_url"]
        predictions = data["predictions"]

        logger.info(f"Sending prediction notifications | url={race_url} | count={len(predictions)}")

        for pred_info in predictions:
            agent_name = pred_info["agent_name"]
            prediction_id = pred_info["prediction_id"]

            prediction = self.prediction_repo.get_prediction(prediction_id)
            if not prediction:
                logger.warning(f"Prediction not found | prediction_id={prediction_id}")
                continue

            message = self._format_prediction_message(prediction)
            message_id = await self.send_message(message)

            if message_id:
                self.prediction_repo.update_telegram_message_id(prediction_id, message_id)

            logger.info(f"Sent prediction | agent={agent_name} | prediction_id={prediction_id} | msg_id={message_id}")

    async def handle_results_evaluated(self, data: dict):
        """Handle results evaluation notification."""
        race_url = data["race_url"]
        predictions = data["predictions"]

        logger.info(f"Sending result notifications | url={race_url} | count={len(predictions)}")

        for pred_info in predictions:
            agent_name = pred_info["agent_name"]
            prediction_id = pred_info["prediction_id"]

            prediction = self.prediction_repo.get_prediction(prediction_id)
            outcome = self.outcome_repo.get_outcome(prediction_id)

            if not prediction or not outcome:
                logger.warning(f"Prediction or outcome not found | prediction_id={prediction_id}")
                continue

            reply_to = self.prediction_repo.get_telegram_message_id(prediction_id)
            message = self._format_result_message(prediction, outcome)
            await self.send_message(message, reply_to_message_id=reply_to)
            logger.info(f"Sent result | agent={agent_name} | prediction_id={prediction_id} | reply_to={reply_to}")

    # ─────────────────────────────────────────────────────────────────
    # Message formatters (unchanged from original)
    # ─────────────────────────────────────────────────────────────────

    def _format_prediction_message(self, prediction: dict) -> str:
        """Format prediction as Telegram message."""
        structured_bet = prediction["structured_bet"]
        race_location = prediction["race_location"]
        race_number = prediction["race_number"]
        agent_id = prediction["agent_id"]
        odds_snapshot = prediction.get("odds_snapshot", {})

        agent_names = {1: "Gemini", 2: "Grok"}
        agent_name = agent_names.get(agent_id, f"Agent {agent_id}")
        race_url = prediction.get("race_url", "")

        lines = [
            f"<b>🏇 New Prediction - {agent_name}</b>",
            f"<b>Race:</b> {race_location} R{race_number}",
            f"<a href=\"{race_url}\">📎 Race Page</a>",
            f"<b>Confidence:</b> {prediction['confidence_score']:.1%}",
            f"<b>Risk Level:</b> {prediction['risk_level'].capitalize()}",
            "",
            f"<b>Analysis:</b>",
            prediction['analysis_summary'][:300] + "..." if len(prediction['analysis_summary']) > 300 else prediction['analysis_summary'],
            ""
        ]

        lines.append("<b>Recommended Bets:</b>")
        total_bet = 0
        total_potential = 0

        if structured_bet.get("win_bet"):
            bet = structured_bet["win_bet"]
            horse_num = str(bet['horse_number'])
            odds = odds_snapshot.get("win", {}).get(horse_num, 0)
            potential = bet['amount'] * odds if odds else 0
            total_bet += bet['amount']
            total_potential += potential
            odds_str = f"@{odds:.2f}" if odds else "@N/A"
            lines.append(f"  💰 Win #{bet['horse_number']} {odds_str} → ${bet['amount']:.0f} (pot: ${potential:.0f})")

        if structured_bet.get("place_bet"):
            bet = structured_bet["place_bet"]
            horse_num = str(bet['horse_number'])
            odds = odds_snapshot.get("place", {}).get(horse_num, 0)
            potential = bet['amount'] * odds if odds else 0
            total_bet += bet['amount']
            total_potential += potential
            odds_str = f"@{odds:.2f}" if odds else "@N/A"
            lines.append(f"  📍 Place #{bet['horse_number']} {odds_str} → ${bet['amount']:.0f} (pot: ${potential:.0f})")

        if structured_bet.get("exacta_bet"):
            bet = structured_bet["exacta_bet"]
            total_bet += bet['amount']
            lines.append(f"  🎯 Exacta {bet['first']}-{bet['second']} - ${bet['amount']:.0f}")

        if structured_bet.get("quinella_bet"):
            bet = structured_bet["quinella_bet"]
            horses = sorted(bet['horses'])
            total_bet += bet['amount']
            lines.append(f"  🔄 Quinella {horses[0]}/{horses[1]} - ${bet['amount']:.0f}")

        if structured_bet.get("trifecta_bet"):
            bet = structured_bet["trifecta_bet"]
            total_bet += bet['amount']
            lines.append(f"  🏆 Trifecta {bet['first']}-{bet['second']}-{bet['third']} - ${bet['amount']:.0f}")

        if structured_bet.get("first4_bet"):
            bet = structured_bet["first4_bet"]
            order = "-".join(map(str, bet['horses']))
            total_bet += bet['amount']
            lines.append(f"  👑 First4 {order} - ${bet['amount']:.0f}")

        if structured_bet.get("qps_bet"):
            bet = structured_bet["qps_bet"]
            horses = "/".join(map(str, sorted(bet['horses'])))
            total_bet += bet['amount']
            lines.append(f"  ⭐ QPS {horses} - ${bet['amount']:.0f}")

        lines.append("")
        lines.append(f"<b>Total:</b> ${total_bet:.0f} | <b>Potential:</b> ${total_potential:.0f}")

        if prediction.get("key_factors"):
            lines.append("")
            lines.append("<b>Key Factors:</b>")
            for factor in prediction["key_factors"][:3]:
                lines.append(f"  • {factor}")

        return "\n".join(lines)

    def _format_result_message(self, prediction: dict, outcome: dict) -> str:
        """Format result as Telegram message."""
        structured_bet = prediction["structured_bet"]
        race_location = prediction["race_location"]
        race_number = prediction["race_number"]
        agent_id = prediction["agent_id"]
        odds_snapshot = prediction.get("odds_snapshot", {})
        actual_dividends = outcome.get("actual_dividends", {})

        agent_names = {1: "Gemini", 2: "Grok"}
        agent_name = agent_names.get(agent_id, f"Agent {agent_id}")

        total_bet = outcome["total_bet_amount"]
        total_payout = outcome["total_payout"]
        profit_loss = outcome["net_profit_loss"]

        if profit_loss > 0:
            result_emoji, result_text = "✅", "PROFIT"
        elif profit_loss == 0:
            result_emoji, result_text = "➖", "BREAK EVEN"
        else:
            result_emoji, result_text = "❌", "LOSS"

        lines = [
            f"<b>{result_emoji} Race Result - {agent_name}</b>",
            f"<b>Race:</b> {race_location} R{race_number}",
            "",
            f"<b>Total Bet:</b> ${total_bet:.2f}",
            f"<b>Total Won:</b> ${total_payout:.2f}",
            f"<b>{result_text}:</b> ${profit_loss:+.2f}",
            ""
        ]

        bet_results = outcome["bet_results"]
        payouts = outcome["payouts"]

        lines.append("<b>Bet Results:</b>")

        if bet_results.get("win") is not None:
            won = bet_results["win"]
            emoji = "✅" if won else "❌"
            if structured_bet.get("win_bet"):
                horse_num = str(structured_bet["win_bet"]["horse_number"])
                predicted_odds = odds_snapshot.get("win", {}).get(horse_num, 0)
                actual_odds = list(actual_dividends.get("win", {}).values())[0] if actual_dividends.get("win") else 0
                payout = payouts.get("win", 0)
                pred_str = f"@{predicted_odds:.2f}" if predicted_odds else "@N/A"
                actual_str = f"@{actual_odds:.2f}" if actual_odds else "@N/A"
                if won and payout > 0:
                    lines.append(f"  {emoji} Win: {pred_str} → {actual_str} = +${payout:.2f}")
                else:
                    lines.append(f"  {emoji} Win: {pred_str} → {actual_str}")

        if bet_results.get("place") is not None:
            won = bet_results["place"]
            emoji = "✅" if won else "❌"
            if structured_bet.get("place_bet"):
                horse_num = str(structured_bet["place_bet"]["horse_number"])
                predicted_odds = odds_snapshot.get("place", {}).get(horse_num, 0)
                actual_odds = actual_dividends.get("place", {}).get(horse_num, 0)
                payout = payouts.get("place", 0)
                pred_str = f"@{predicted_odds:.2f}" if predicted_odds else "@N/A"
                actual_str = f"@{actual_odds:.2f}" if actual_odds else "@N/A"
                if won and payout > 0:
                    lines.append(f"  {emoji} Place: {pred_str} → {actual_str} = +${payout:.2f}")
                else:
                    lines.append(f"  {emoji} Place: {pred_str} → {actual_str}")

        for bet_type in ["exacta", "quinella", "trifecta", "first4", "qps"]:
            if bet_results.get(bet_type) is not None:
                won = bet_results[bet_type]
                emoji = "✅" if won else "❌"
                bet_type_display = bet_type.replace("_", " ").title()
                payout = payouts.get(bet_type, 0)
                if won and payout > 0:
                    lines.append(f"  {emoji} {bet_type_display}: +${payout:.2f}")
                else:
                    lines.append(f"  {emoji} {bet_type_display}")

        if outcome.get("finishing_order"):
            lines.append("")
            lines.append("<b>Finishing Order:</b>")
            for i, horse in enumerate(outcome["finishing_order"][:4], 1):
                horse_num = horse.get("number", "?")
                horse_name = horse.get("name", "Unknown")
                lines.append(f"  {i}. #{horse_num} {horse_name}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────
    # Evaluate helper (unchanged from original)
    # ─────────────────────────────────────────────────────────────────

    async def _evaluate_prediction_for_cmd(self, prediction: dict, race_result) -> bool:
        """Evaluate a prediction and save outcome. Returns True if evaluated."""
        structured_bet = prediction["structured_bet"]
        finishing_order = race_result.finishing_order

        if not finishing_order:
            return False

        winner = finishing_order[0] if len(finishing_order) > 0 else None
        second = finishing_order[1] if len(finishing_order) > 1 else None
        third = finishing_order[2] if len(finishing_order) > 2 else None

        bet_results = {}
        payouts = {}

        if structured_bet.get("win_bet"):
            win_bet = structured_bet["win_bet"]
            horse_num = win_bet["horse_number"]
            is_win = winner and winner.get("number") == horse_num
            bet_results["win"] = is_win
            if is_win and winner:
                odds = winner.get("fixed_win", 0) or winner.get("tote_win", 0)
                payouts["win"] = win_bet["amount"] * odds

        if structured_bet.get("place_bet"):
            place_bet = structured_bet["place_bet"]
            horse_num = place_bet["horse_number"]
            placed_horses = [h.get("number") for h in finishing_order[:3] if h]
            is_place = horse_num in placed_horses
            bet_results["place"] = is_place
            if is_place:
                for horse in finishing_order[:3]:
                    if horse.get("number") == horse_num:
                        odds = horse.get("fixed_place", 0) or horse.get("tote_place", 0)
                        payouts["place"] = place_bet["amount"] * odds
                        break

        if structured_bet.get("exacta_bet"):
            exacta_bet = structured_bet["exacta_bet"]
            is_exacta = (
                winner and second and
                winner.get("number") == exacta_bet["first"] and
                second.get("number") == exacta_bet["second"]
            )
            bet_results["exacta"] = is_exacta
            if is_exacta and race_result.dividends.get("exacta"):
                div = race_result.dividends["exacta"]
                div_val = div.get("amount", 0) if isinstance(div, dict) else div
                payouts["exacta"] = exacta_bet["amount"] * float(div_val)

        if structured_bet.get("quinella_bet"):
            quinella_bet = structured_bet["quinella_bet"]
            horses = set(quinella_bet["horses"])
            top_two = {winner.get("number"), second.get("number")} if winner and second else set()
            is_quinella = horses == top_two
            bet_results["quinella"] = is_quinella
            if is_quinella and race_result.dividends.get("quinella"):
                div = race_result.dividends["quinella"]
                div_val = div.get("amount", 0) if isinstance(div, dict) else div
                payouts["quinella"] = quinella_bet["amount"] * float(div_val)

        if structured_bet.get("trifecta_bet"):
            trifecta_bet = structured_bet["trifecta_bet"]
            is_trifecta = (
                winner and second and third and
                winner.get("number") == trifecta_bet["first"] and
                second.get("number") == trifecta_bet["second"] and
                third.get("number") == trifecta_bet["third"]
            )
            bet_results["trifecta"] = is_trifecta
            if is_trifecta and race_result.dividends.get("trifecta"):
                div = race_result.dividends["trifecta"]
                div_val = div.get("amount", 0) if isinstance(div, dict) else div
                payouts["trifecta"] = trifecta_bet["amount"] * float(div_val)

        if structured_bet.get("first4_bet"):
            first4_bet = structured_bet["first4_bet"]
            actual_order = [h.get("number") for h in finishing_order[:4] if h]
            is_first4 = first4_bet["horses"] == actual_order
            bet_results["first4"] = is_first4
            if is_first4 and race_result.dividends.get("first4"):
                div = race_result.dividends["first4"]
                div_val = div.get("amount", 0) if isinstance(div, dict) else div
                payouts["first4"] = first4_bet["amount"] * float(div_val)

        if structured_bet.get("qps_bet"):
            qps_bet = structured_bet["qps_bet"]
            horses = set(qps_bet["horses"])
            top_three = {h.get("number") for h in finishing_order[:3] if h}
            is_qps = len(horses & top_three) >= 2
            bet_results["qps"] = is_qps
            if is_qps and race_result.dividends.get("qps"):
                div = race_result.dividends["qps"]
                div_val = div.get("amount", 0) if isinstance(div, dict) else div
                payouts["qps"] = qps_bet["amount"] * float(div_val)

        total_bet_amount = sum(
            bet.get("amount", 0)
            for bet_type in ["win_bet", "place_bet", "exacta_bet", "quinella_bet",
                             "trifecta_bet", "first4_bet", "qps_bet"]
            if (bet := structured_bet.get(bet_type))
        )

        actual_dividends = self._build_actual_dividends_for_cmd(race_result, finishing_order)

        self.outcome_repo.save_outcome(
            prediction_id=prediction["prediction_id"],
            finishing_order=finishing_order,
            dividends=race_result.dividends,
            bet_results=bet_results,
            payouts=payouts,
            total_bet_amount=total_bet_amount,
            actual_dividends_json=json.dumps(actual_dividends)
        )

        return True

    def _build_actual_dividends_for_cmd(self, race_result, finishing_order: list) -> dict:
        """Build structured actual dividends."""
        actual = {}
        dividends = race_result.dividends

        if finishing_order and dividends.get("win"):
            winner = finishing_order[0]["number"]
            actual["win"] = {str(winner): dividends["win"]}

        if dividends.get("exacta") and len(finishing_order) >= 2:
            combo = f"{finishing_order[0]['number']}-{finishing_order[1]['number']}"
            div = dividends["exacta"]
            actual["exacta"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

        if dividends.get("quinella") and len(finishing_order) >= 2:
            horses = sorted([finishing_order[0]["number"], finishing_order[1]["number"]])
            combo = f"{horses[0]}-{horses[1]}"
            div = dividends["quinella"]
            actual["quinella"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

        if dividends.get("trifecta") and len(finishing_order) >= 3:
            combo = f"{finishing_order[0]['number']}-{finishing_order[1]['number']}-{finishing_order[2]['number']}"
            div = dividends["trifecta"]
            actual["trifecta"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

        if dividends.get("first4") and len(finishing_order) >= 4:
            combo = "-".join(str(h["number"]) for h in finishing_order[:4])
            div = dividends["first4"]
            actual["first4"] = {combo: div if not isinstance(div, dict) else div.get("amount", 0)}

        return actual

    async def _format_statistics_message(self) -> str:
        """Format agent statistics message."""
        all_stats = self.stats_repo.get_all_statistics()
        lines = ["<b>📊 Agent Statistics</b>", ""]
        for stats in all_stats:
            agent_name = stats["agent_name"].capitalize()
            total_bets = stats["total_bets"]
            total_wins = stats["total_wins"]
            win_rate = (total_wins / total_bets * 100) if total_bets > 0 else 0
            roi = stats["roi_percentage"]
            profit_loss = stats["net_profit_loss"]
            lines.extend([
                f"<b>{agent_name}:</b>",
                f"  Predictions: {stats['total_predictions']}",
                f"  Bets: {total_bets} ({total_wins}W-{stats['total_losses']}L)",
                f"  Win Rate: {win_rate:.1f}%",
                f"  ROI: {roi:+.1f}%",
                f"  P/L: ${profit_loss:+.2f}",
                ""
            ])
        return "\n".join(lines)

    async def shutdown(self):
        """Shutdown the service."""
        if self.pubsub:
            await self.pubsub.unsubscribe("predictions:new", "results:evaluated", "races:digest")
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        await self.bot.session.close()
        logger.info("Telegram service stopped")


async def main():
    """Main entry point."""
    service = TelegramNotificationService()
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
