"""
Results Evaluation Service

Waits for races to finish, fetches results, evaluates predictions, and updates statistics.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis.asyncio as aioredis
from tabtouch_parser import TabTouchParser
from src.config.settings import get_settings
from src.database.repositories import PredictionRepository, OutcomeRepository


class ResultsEvaluationService:
    """Service for evaluating predictions against race results."""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: aioredis.Redis = None
        self.pubsub = None
        self.parser = TabTouchParser(headless=True)

        # Initialize repositories
        self.prediction_repo = PredictionRepository(
            db_path=self.settings.database.path
        )
        self.outcome_repo = OutcomeRepository(
            db_path=self.settings.database.path
        )

        # Track scheduled result checks
        self.scheduled_checks: dict[str, dict] = {}

    async def start(self):
        """Start the results service."""
        # Connect to Redis
        redis_settings = self.settings.redis
        self.redis_client = await aioredis.from_url(
            f"redis://{redis_settings.host}:{redis_settings.port}/{redis_settings.db}",
            password=redis_settings.password if redis_settings.password else None,
            encoding="utf-8",
            decode_responses=True
        )

        # Subscribe to result check scheduling
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe("race:schedule_result_check")

        print(f"✓ Results Evaluation Service started")

        # Restore scheduled checks from database on startup
        restored = await self.restore_scheduled_checks()
        if restored:
            print(f"  Restored {restored} pending result checks from database")

        print(f"  Listening for result checks...")

        async with self.parser:
            # Start both loops
            await asyncio.gather(
                self.listen_loop(),
                self.check_results_loop()
            )

    async def restore_scheduled_checks(self) -> int:
        """Restore scheduled checks from database on startup."""
        import sqlite3

        try:
            conn = sqlite3.connect(self.settings.database.path)
            cursor = conn.cursor()

            # Find all races with predictions but no outcomes
            cursor.execute('''
                SELECT DISTINCT p.race_url, p.race_start_time
                FROM predictions p
                WHERE p.prediction_id NOT IN (
                    SELECT prediction_id FROM prediction_outcomes
                )
                AND p.race_start_time IS NOT NULL
            ''')

            count = 0
            for row in cursor.fetchall():
                race_url, race_start_str = row

                if not race_start_str:
                    continue

                try:
                    # Parse race start time
                    race_start = datetime.fromisoformat(race_start_str.replace('Z', '+00:00'))

                    # Calculate check time (start + wait minutes)
                    check_time = race_start + timedelta(
                        minutes=self.settings.timing.result_wait_minutes
                    )

                    # Only schedule if check time hasn't passed by more than 24 hours
                    now = datetime.now(tz=check_time.tzinfo)
                    if now - check_time < timedelta(hours=24):
                        self.scheduled_checks[race_url] = {
                            "check_time": check_time,
                            "retry_count": 0
                        }
                        count += 1
                except Exception as e:
                    print(f"  ⚠ Error parsing time for {race_url}: {e}")
                    continue

            conn.close()
            return count

        except Exception as e:
            print(f"  ✗ Error restoring scheduled checks: {e}")
            return 0

    async def listen_loop(self):
        """Listen for result check scheduling."""
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    race_url = data["race_url"]
                    check_time = datetime.fromisoformat(data["check_time"])

                    # Schedule the check
                    self.scheduled_checks[race_url] = {
                        "check_time": check_time,
                        "retry_count": 0
                    }

                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scheduled result check:")
                    print(f"  Race: {race_url}")
                    print(f"  Check at: {check_time.strftime('%H:%M:%S')}")

                except Exception as e:
                    print(f"✗ Error scheduling check: {e}")

    async def check_results_loop(self):
        """Periodically check for races that need results evaluation."""
        while True:
            try:
                now = datetime.now(tz=None)
                races_to_check = []

                # Find races ready for checking
                for race_url, check_info in list(self.scheduled_checks.items()):
                    check_time = check_info["check_time"]

                    # Make check_time naive if it has timezone
                    if check_time.tzinfo:
                        check_time = check_time.replace(tzinfo=None)

                    if now >= check_time:
                        races_to_check.append(race_url)

                # Process each race
                for race_url in races_to_check:
                    await self.check_race_results(race_url)

            except Exception as e:
                print(f"✗ Error in check loop: {e}")

            # Check every minute
            await asyncio.sleep(60)

    async def check_race_results(self, race_url: str):
        """Check results for a specific race."""
        check_info = self.scheduled_checks[race_url]
        retry_count = check_info["retry_count"]

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking results:")
        print(f"  Race: {race_url}")
        print(f"  Attempt: {retry_count + 1}/{self.settings.timing.result_max_retries}")

        try:
            # Try to fetch results
            race_result = await self.parser.get_race_results(race_url)

            if race_result and race_result.finishing_order:
                print(f"  ✓ Results found!")

                # Get predictions for this race
                predictions = self.prediction_repo.get_predictions_for_race(race_url)

                if predictions:
                    print(f"  Evaluating {len(predictions)} predictions...")

                    for pred in predictions:
                        await self.evaluate_prediction(pred, race_result)

                    # Publish evaluation complete
                    await self.publish_evaluation_complete(race_url, predictions)

                # Remove from scheduled checks
                del self.scheduled_checks[race_url]

            else:
                # Results not available yet
                print(f"  ⚠ Results not available yet")
                await self.retry_or_abandon(race_url)

        except Exception as e:
            print(f"  ✗ Error fetching results: {e}")
            await self.retry_or_abandon(race_url)

    async def retry_or_abandon(self, race_url: str):
        """Retry or abandon result check."""
        check_info = self.scheduled_checks[race_url]
        check_info["retry_count"] += 1

        if check_info["retry_count"] >= self.settings.timing.result_max_retries:
            print(f"  ✗ Max retries reached, abandoning")
            del self.scheduled_checks[race_url]
        else:
            # Schedule next retry
            next_check = datetime.now() + timedelta(
                seconds=self.settings.timing.result_retry_interval
            )
            check_info["check_time"] = next_check
            print(f"  ⏰ Next check at: {next_check.strftime('%H:%M:%S')}")

    async def evaluate_prediction(self, prediction: dict, race_result):
        """Evaluate a single prediction against results."""
        prediction_id = prediction["prediction_id"]
        agent_name = prediction["agent_name"]
        structured_bet = prediction["structured_bet"]

        print(f"    Evaluating {agent_name} prediction #{prediction_id}...")

        # Parse finishing order
        finishing_order = race_result.finishing_order
        if not finishing_order:
            print(f"    ✗ No finishing order available")
            return

        # Extract positions
        winner = finishing_order[0] if len(finishing_order) > 0 else None
        second = finishing_order[1] if len(finishing_order) > 1 else None
        third = finishing_order[2] if len(finishing_order) > 2 else None
        fourth = finishing_order[3] if len(finishing_order) > 3 else None

        # Evaluate each bet type
        bet_results = {}
        payouts = {}

        # Win bet
        if structured_bet.get("win_bet"):
            win_bet = structured_bet["win_bet"]
            horse_num = win_bet["horse_number"]
            is_win = winner and winner.get("number") == horse_num

            bet_results["win"] = is_win
            if is_win and winner:
                # Calculate payout (bet_amount * odds)
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
                # Find the horse and get place odds
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
                payouts["exacta"] = exacta_bet["amount"] * race_result.dividends["exacta"]

        # Quinella bet
        if structured_bet.get("quinella_bet"):
            quinella_bet = structured_bet["quinella_bet"]
            horses = set(quinella_bet["horses"])
            top_two = {winner.get("number"), second.get("number")} if winner and second else set()
            is_quinella = horses == top_two

            bet_results["quinella"] = is_quinella
            if is_quinella and race_result.dividends.get("quinella"):
                payouts["quinella"] = quinella_bet["amount"] * race_result.dividends["quinella"]

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
                payouts["trifecta"] = trifecta_bet["amount"] * race_result.dividends["trifecta"]

        # First4 bet
        if structured_bet.get("first4_bet"):
            first4_bet = structured_bet["first4_bet"]
            actual_order = [h.get("number") for h in finishing_order[:4] if h]
            is_first4 = first4_bet["horses"] == actual_order

            bet_results["first4"] = is_first4
            if is_first4 and race_result.dividends.get("first4"):
                payouts["first4"] = first4_bet["amount"] * race_result.dividends["first4"]

        # QPS bet
        if structured_bet.get("qps_bet"):
            qps_bet = structured_bet["qps_bet"]
            horses = set(qps_bet["horses"])
            top_three = {h.get("number") for h in finishing_order[:3] if h}
            # Any 2 of the selected horses in top 3
            is_qps = len(horses & top_three) >= 2

            bet_results["qps"] = is_qps
            if is_qps and race_result.dividends.get("qps"):
                payouts["qps"] = qps_bet["amount"] * race_result.dividends.get("qps", 0)

        # Calculate total bet amount
        total_bet_amount = sum(
            bet.get("amount", 0)
            for bet_type in ["win_bet", "place_bet", "exacta_bet", "quinella_bet",
                             "trifecta_bet", "first4_bet", "qps_bet"]
            if (bet := structured_bet.get(bet_type))
        )

        # Save outcome
        outcome_id = self.outcome_repo.save_outcome(
            prediction_id=prediction_id,
            finishing_order=finishing_order,
            dividends=race_result.dividends,
            bet_results=bet_results,
            payouts=payouts,
            total_bet_amount=total_bet_amount
        )

        # Print summary
        total_payout = sum(payouts.values())
        profit_loss = total_payout - total_bet_amount
        print(f"    ✓ {agent_name}: Bet ${total_bet_amount:.2f}, "
              f"Won ${total_payout:.2f}, "
              f"P/L: ${profit_loss:+.2f}")

    async def publish_evaluation_complete(self, race_url: str, predictions: list[dict]):
        """Publish evaluation completion to Telegram service."""
        message = {
            "race_url": race_url,
            "predictions": [
                {"agent_name": p["agent_name"], "prediction_id": p["prediction_id"]}
                for p in predictions
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.redis_client.publish(
            "results:evaluated",
            json.dumps(message)
        )

    async def shutdown(self):
        """Shutdown the service."""
        if self.pubsub:
            await self.pubsub.unsubscribe("race:schedule_result_check")
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        await self.parser.__aexit__(None, None, None)
        print("\n✓ Results service stopped")


async def main():
    """Main entry point."""
    service = ResultsEvaluationService()
    try:
        await service.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
