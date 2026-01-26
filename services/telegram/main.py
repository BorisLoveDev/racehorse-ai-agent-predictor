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
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config.settings import get_settings
from src.database.repositories import (
    PredictionRepository,
    OutcomeRepository,
    StatisticsRepository
)


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
        print(f"  Listening for notifications...")

        # Start listening loop
        await self.listen_loop()

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

        # Send updated statistics
        stats_message = await self._format_statistics_message()
        await self.send_message(stats_message)
        print(f"  ✓ Sent statistics update")

    def _format_prediction_message(self, prediction: dict) -> str:
        """Format prediction as Telegram message."""
        structured_bet = prediction["structured_bet"]
        race_location = prediction["race_location"]
        race_number = prediction["race_number"]
        agent_id = prediction["agent_id"]

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

        # Add bets
        lines.append("<b>Recommended Bets:</b>")

        if structured_bet.get("win_bet"):
            bet = structured_bet["win_bet"]
            lines.append(f"  💰 Win #{bet['horse_number']} - ${bet['amount']:.0f}")

        if structured_bet.get("place_bet"):
            bet = structured_bet["place_bet"]
            lines.append(f"  📍 Place #{bet['horse_number']} - ${bet['amount']:.0f}")

        if structured_bet.get("exacta_bet"):
            bet = structured_bet["exacta_bet"]
            lines.append(f"  🎯 Exacta {bet['first']}-{bet['second']} - ${bet['amount']:.0f}")

        if structured_bet.get("quinella_bet"):
            bet = structured_bet["quinella_bet"]
            horses = sorted(bet['horses'])
            lines.append(f"  🔄 Quinella {horses[0]}/{horses[1]} - ${bet['amount']:.0f}")

        if structured_bet.get("trifecta_bet"):
            bet = structured_bet["trifecta_bet"]
            lines.append(f"  🏆 Trifecta {bet['first']}-{bet['second']}-{bet['third']} - ${bet['amount']:.0f}")

        if structured_bet.get("first4_bet"):
            bet = structured_bet["first4_bet"]
            order = "-".join(map(str, bet['horses']))
            lines.append(f"  👑 First4 {order} - ${bet['amount']:.0f}")

        if structured_bet.get("qps_bet"):
            bet = structured_bet["qps_bet"]
            horses = "/".join(map(str, sorted(bet['horses'])))
            lines.append(f"  ⭐ QPS {horses} - ${bet['amount']:.0f}")

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

        # Add bet results
        bet_results = outcome["bet_results"]
        payouts = outcome["payouts"]

        lines.append("<b>Bet Results:</b>")

        for bet_type, won in bet_results.items():
            if won is None:
                continue

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
