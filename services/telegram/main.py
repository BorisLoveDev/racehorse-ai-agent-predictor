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
from src.logging_config import setup_logging

# Initialize logger
logger = setup_logging("telegram")


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
            logger.info(f"Received /start from chat_id={message.chat.id}")
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
                "/evaluate - Manually check results for pending bets",
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
                "/evaluate - Manually check pending bets",
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

                # Group by race_url
                races = {}
                for pred in pending:
                    url = pred["race_url"]
                    if url not in races:
                        races[url] = []
                    races[url].append(pred)

                await message.answer(f"Found {len(pending)} predictions across {len(races)} races")

                # Initialize parser if needed
                if not self.parser:
                    self.parser = TabTouchParser(headless=True)
                    await self.parser.__aenter__()

                evaluated = 0
                skipped = 0

                for race_url, predictions in races.items():
                    try:
                        race_result = await self.parser.get_race_results(race_url)

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

    async def _evaluate_prediction_for_cmd(self, prediction: dict, race_result) -> bool:
        """Evaluate a prediction and save outcome. Returns True if evaluated."""
        import json

        structured_bet = prediction["structured_bet"]
        finishing_order = race_result.finishing_order

        if not finishing_order:
            return False

        winner = finishing_order[0] if len(finishing_order) > 0 else None
        second = finishing_order[1] if len(finishing_order) > 1 else None
        third = finishing_order[2] if len(finishing_order) > 2 else None

        bet_results = {}
        payouts = {}

        # Win bet
        if structured_bet.get("win_bet"):
            win_bet = structured_bet["win_bet"]
            horse_num = win_bet["horse_number"]
            is_win = winner and winner.get("number") == horse_num
            bet_results["win"] = is_win
            if is_win and winner:
                odds = winner.get("fixed_win", 0) or winner.get("tote_win", 0)
                payouts["win"] = win_bet["amount"] * odds

        # Place bet
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

        # Exacta bet
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
                div_val = div if not isinstance(div, dict) else div.get("amount", 0)
                if isinstance(div_val, str):
                    div_val = float(div_val.replace("$", "").replace(",", ""))
                payouts["exacta"] = exacta_bet["amount"] * div_val

        # Quinella bet
        if structured_bet.get("quinella_bet"):
            quinella_bet = structured_bet["quinella_bet"]
            horses = set(quinella_bet["horses"])
            top_two = {winner.get("number"), second.get("number")} if winner and second else set()
            is_quinella = horses == top_two
            bet_results["quinella"] = is_quinella
            if is_quinella and race_result.dividends.get("quinella"):
                div = race_result.dividends["quinella"]
                div_val = div if not isinstance(div, dict) else div.get("amount", 0)
                if isinstance(div_val, str):
                    div_val = float(div_val.replace("$", "").replace(",", ""))
                payouts["quinella"] = quinella_bet["amount"] * div_val

        # Trifecta bet
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
                div_val = div if not isinstance(div, dict) else div.get("amount", 0)
                if isinstance(div_val, str):
                    div_val = float(div_val.replace("$", "").replace(",", ""))
                payouts["trifecta"] = trifecta_bet["amount"] * div_val

        # First4 bet
        if structured_bet.get("first4_bet"):
            first4_bet = structured_bet["first4_bet"]
            fourth = finishing_order[3] if len(finishing_order) > 3 else None
            actual_order = [h.get("number") for h in finishing_order[:4] if h]
            is_first4 = first4_bet["horses"] == actual_order
            bet_results["first4"] = is_first4
            if is_first4 and race_result.dividends.get("first4"):
                div = race_result.dividends["first4"]
                div_val = div if not isinstance(div, dict) else div.get("amount", 0)
                if isinstance(div_val, str):
                    div_val = float(div_val.replace("$", "").replace(",", ""))
                payouts["first4"] = first4_bet["amount"] * div_val

        # QPS bet
        if structured_bet.get("qps_bet"):
            qps_bet = structured_bet["qps_bet"]
            horses = set(qps_bet["horses"])
            top_three = {h.get("number") for h in finishing_order[:3] if h}
            is_qps = len(horses & top_three) >= 2
            bet_results["qps"] = is_qps
            if is_qps and race_result.dividends.get("qps"):
                div = race_result.dividends["qps"]
                div_val = div if not isinstance(div, dict) else div.get("amount", 0)
                if isinstance(div_val, str):
                    div_val = float(div_val.replace("$", "").replace(",", ""))
                payouts["qps"] = qps_bet["amount"] * div_val

        # Calculate total bet amount
        total_bet_amount = sum(
            bet.get("amount", 0)
            for bet_type in ["win_bet", "place_bet", "exacta_bet", "quinella_bet",
                             "trifecta_bet", "first4_bet", "qps_bet"]
            if (bet := structured_bet.get(bet_type))
        )

        # Build actual dividends
        actual_dividends = self._build_actual_dividends_for_cmd(race_result, finishing_order)

        # Save outcome
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

        logger.info("Telegram Notification Service started")
        logger.info(f"Chat ID: {self.chat_id}")
        logger.info("Listening for notifications and commands...")

        # Verify bot connection
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"Bot connected | username=@{bot_info.username} | id={bot_info.id}")
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}", exc_info=True)
            return

        # Start both polling (for commands) and listening (for Redis)
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

                except Exception as e:
                    logger.error(f"Error processing notification: {e}", exc_info=True)

    async def handle_new_predictions(self, data: dict):
        """Handle new prediction notification."""
        race_url = data["race_url"]
        predictions = data["predictions"]

        logger.info(f"Sending prediction notifications | url={race_url} | count={len(predictions)}")

        for pred_info in predictions:
            agent_name = pred_info["agent_name"]
            prediction_id = pred_info["prediction_id"]

            # Get full prediction data
            prediction = self.prediction_repo.get_prediction(prediction_id)
            if not prediction:
                logger.warning(f"Prediction not found | prediction_id={prediction_id}")
                continue

            # Format and send message
            message = self._format_prediction_message(prediction)
            await self.send_message(message)
            logger.info(f"Sent prediction | agent={agent_name} | prediction_id={prediction_id}")

    async def handle_results_evaluated(self, data: dict):
        """Handle results evaluation notification."""
        race_url = data["race_url"]
        predictions = data["predictions"]

        logger.info(f"Sending result notifications | url={race_url} | count={len(predictions)}")

        for pred_info in predictions:
            agent_name = pred_info["agent_name"]
            prediction_id = pred_info["prediction_id"]

            # Get prediction and outcome
            prediction = self.prediction_repo.get_prediction(prediction_id)
            outcome = self.outcome_repo.get_outcome(prediction_id)

            if not prediction or not outcome:
                logger.warning(f"Prediction or outcome not found | prediction_id={prediction_id}")
                continue

            # Format and send message
            message = self._format_result_message(prediction, outcome)
            await self.send_message(message)
            logger.info(f"Sent result | agent={agent_name} | prediction_id={prediction_id}")

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
            logger.error(f"Failed to send Telegram message: {e}", exc_info=True)

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
