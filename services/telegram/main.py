"""
Telegram Notification Service

Sends notifications about predictions and results to Telegram.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from tabtouch_parser import TabTouchParser

from src.config.settings import get_settings
from src.database.repositories import (
    PredictionRepository,
    OutcomeRepository,
    StatisticsRepository
)
from services.telegram.charts import generate_pl_chart


class TelegramNotificationService:
    """Service for sending Telegram notifications."""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: aioredis.Redis = None
        self.pubsub = None

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

        # Initialize dispatcher for commands
        self.dp = Dispatcher()
        self.router = Router()
        self._setup_commands()
        self.dp.include_router(self.router)

        # Initialize parser for /races command
        self.parser = None

    def _setup_commands(self):
        """Setup command handlers."""

        @self.router.message(Command("start"))
        async def cmd_start(message: Message):
            """Handle /start command."""
            print(f"[DEBUG] Received /start from chat {message.chat.id}")
            lines = [
                "<b>🏇 Racehorse Betting Agent</b>",
                "",
                "I analyze horse races and provide betting predictions.",
                "",
                "<b>Available commands:</b>",
                "/races - Show upcoming races",
                "/status - Show active bets awaiting results",
                "/history [N] - Show last N results (default 5)",
                "/stats [period] - Statistics (all|today|3d|week)",
                "",
                "Predictions are sent automatically before each race."
            ]
            await message.answer("\n".join(lines))

        @self.router.message(Command("help"))
        async def cmd_help(message: Message):
            """Handle /help command."""
            lines = [
                "<b>📖 Help</b>",
                "",
                "<b>Commands:</b>",
                "/start - Welcome message",
                "/races - Show upcoming races",
                "/status - Show active bets awaiting results",
                "/history [N] - Show last N results",
                "/stats [period] - Statistics with P/L chart",
                "",
                "<b>Stats periods:</b>",
                "• all - All time (default)",
                "• today - Today only",
                "• 3d - Last 3 days",
                "• week - This week"
            ]
            await message.answer("\n".join(lines))

        @self.router.message(Command("races"))
        async def cmd_races(message: Message):
            """Show upcoming races."""
            if not self.parser:
                self.parser = TabTouchParser(headless=True)
                await self.parser.__aenter__()

            try:
                races = await self.parser.get_next_races()
                lines = ["<b>🏇 Upcoming Races:</b>", ""]

                for race in races[:10]:
                    time_str = race.time_parsed.strftime("%H:%M") if race.time_parsed else "?"
                    lines.append(f"• {race.location} R{race.race_number} — {time_str}")

                await message.answer("\n".join(lines))
            except Exception as e:
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
                await message.answer(f"Error fetching status: {e}")

        @self.router.message(Command("history"))
        async def cmd_history(message: Message):
            """Show last N results (default 5)."""
            try:
                args = message.text.split()
                limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
                limit = min(limit, 20)  # Max 20

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

                stats_list = self.stats_repo.get_statistics_for_period(period)

                period_display = {
                    "all": "All Time",
                    "today": "Today",
                    "3d": "Last 3 Days",
                    "week": "This Week"
                }

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

                stats_text = "\n".join(lines)

                # Generate and send chart
                chart_data = self.stats_repo.get_pl_chart_data(period)
                if chart_data:
                    chart_buf = generate_pl_chart(chart_data, period_display[period])
                    photo = BufferedInputFile(chart_buf.read(), filename="pl_chart.png")
                    await message.answer_photo(photo=photo, caption=stats_text)
                else:
                    # No chart data, just send stats text
                    await message.answer(stats_text)

            except Exception as e:
                await message.answer(f"Error fetching statistics: {e}")

    async def start(self):
        """Start the Telegram service."""
        # Connect to Redis
        redis_settings = self.settings.redis
        self.redis_client = await aioredis.from_url(
            f"redis://{redis_settings.host}:{redis_settings.port}/{redis_settings.db}",
            password=redis_settings.password if redis_settings.password else None,
            encoding="utf-8",
            decode_responses=True
        )

        # Subscribe to channels
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(
            "predictions:new",
            "results:evaluated"
        )

        print(f"✓ Telegram Notification Service started")
        print(f"  Chat ID: {self.chat_id}")
        print(f"  Listening for notifications and commands...")

        # Verify bot connection
        try:
            bot_info = await self.bot.get_me()
            print(f"  Bot: @{bot_info.username} (ID: {bot_info.id})")
        except Exception as e:
            print(f"  ✗ Failed to connect to Telegram: {e}")
            return

        # Start both polling (for commands) and listening (for Redis)
        print("  Starting polling...")
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

                except Exception as e:
                    print(f"✗ Error processing notification: {e}")

    async def handle_new_predictions(self, data: dict):
        """Handle new prediction notification."""
        race_url = data["race_url"]
        predictions = data["predictions"]

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sending prediction notifications...")

        for pred_info in predictions:
            agent_name = pred_info["agent_name"]
            prediction_id = pred_info["prediction_id"]

            # Get full prediction data
            prediction = self.prediction_repo.get_prediction(prediction_id)
            if not prediction:
                continue

            # Format and send message
            message = self._format_prediction_message(prediction)
            await self.send_message(message)
            print(f"  ✓ Sent {agent_name} prediction")

    async def handle_results_evaluated(self, data: dict):
        """Handle results evaluation notification."""
        race_url = data["race_url"]
        predictions = data["predictions"]

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sending result notifications...")

        for pred_info in predictions:
            agent_name = pred_info["agent_name"]
            prediction_id = pred_info["prediction_id"]

            # Get prediction and outcome
            prediction = self.prediction_repo.get_prediction(prediction_id)
            outcome = self.outcome_repo.get_outcome(prediction_id)

            if not prediction or not outcome:
                continue

            # Format and send message
            message = self._format_result_message(prediction, outcome)
            await self.send_message(message)
            print(f"  ✓ Sent {agent_name} result")

    def _format_prediction_message(self, prediction: dict) -> str:
        """Format prediction as Telegram message."""
        structured_bet = prediction["structured_bet"]
        race_location = prediction["race_location"]
        race_number = prediction["race_number"]
        agent_id = prediction["agent_id"]
        odds_snapshot = prediction.get("odds_snapshot", {})

        # Map agent_id to name
        agent_names = {1: "Gemini", 2: "Grok"}
        agent_name = agent_names.get(agent_id, f"Agent {agent_id}")

        lines = [
            f"<b>🏇 New Prediction - {agent_name}</b>",
            f"<b>Race:</b> {race_location} R{race_number}",
            f"<b>Confidence:</b> {prediction['confidence_score']:.1%}",
            f"<b>Risk Level:</b> {prediction['risk_level'].capitalize()}",
            "",
            f"<b>Analysis:</b>",
            prediction['analysis_summary'][:300] + "..." if len(prediction['analysis_summary']) > 300 else prediction['analysis_summary'],
            ""
        ]

        # Add bets with odds and potential payouts
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

        # Add totals
        lines.append("")
        lines.append(f"<b>Total:</b> ${total_bet:.0f} | <b>Potential:</b> ${total_potential:.0f}")

        # Key factors
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

        # Map agent_id to name
        agent_names = {1: "Gemini", 2: "Grok"}
        agent_name = agent_names.get(agent_id, f"Agent {agent_id}")

        total_bet = outcome["total_bet_amount"]
        total_payout = outcome["total_payout"]
        profit_loss = outcome["net_profit_loss"]

        # Result emoji
        if profit_loss > 0:
            result_emoji = "✅"
            result_text = "PROFIT"
        elif profit_loss == 0:
            result_emoji = "➖"
            result_text = "BREAK EVEN"
        else:
            result_emoji = "❌"
            result_text = "LOSS"

        lines = [
            f"<b>{result_emoji} Race Result - {agent_name}</b>",
            f"<b>Race:</b> {race_location} R{race_number}",
            "",
            f"<b>Total Bet:</b> ${total_bet:.2f}",
            f"<b>Total Won:</b> ${total_payout:.2f}",
            f"<b>{result_text}:</b> ${profit_loss:+.2f}",
            ""
        ]

        # Add bet results with odds comparison
        bet_results = outcome["bet_results"]
        payouts = outcome["payouts"]

        lines.append("<b>Bet Results:</b>")

        # Win bet
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

        # Place bet
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

        # Other bet types (no odds comparison)
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

        # Finishing order
        if outcome.get("finishing_order"):
            lines.append("")
            lines.append("<b>Finishing Order:</b>")
            for i, horse in enumerate(outcome["finishing_order"][:4], 1):
                horse_num = horse.get("number", "?")
                horse_name = horse.get("name", "Unknown")
                lines.append(f"  {i}. #{horse_num} {horse_name}")

        return "\n".join(lines)

    async def _format_statistics_message(self) -> str:
        """Format agent statistics message."""
        all_stats = self.stats_repo.get_all_statistics()

        lines = [
            "<b>📊 Agent Statistics</b>",
            ""
        ]

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

    async def send_message(self, text: str):
        """Send a message to Telegram."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text
            )
        except Exception as e:
            print(f"✗ Failed to send Telegram message: {e}")

    async def shutdown(self):
        """Shutdown the service."""
        if self.pubsub:
            await self.pubsub.unsubscribe("predictions:new", "results:evaluated")
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        if self.parser:
            await self.parser.__aexit__(None, None, None)
        await self.bot.session.close()
        print("\n✓ Telegram service stopped")


async def main():
    """Main entry point."""
    service = TelegramNotificationService()
    try:
        await service.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
