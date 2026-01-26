"""
Agent Orchestrator Service

Listens for races ready for analysis, runs both AI agents, and saves predictions.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import redis.asyncio as aioredis
from src.agents.gemini_agent import GeminiAgent
from src.agents.grok_agent import GrokAgent
from src.config.settings import get_settings
from src.database.repositories import PredictionRepository


class AgentOrchestratorService:
    """Service for running AI agents on races."""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: aioredis.Redis = None
        self.pubsub = None

        # Initialize agents
        print("Initializing AI agents...")
        self.gemini_agent = GeminiAgent()
        self.grok_agent = GrokAgent()
        print("✓ Agents initialized")

        # Initialize database repository
        self.prediction_repo = PredictionRepository(
            db_path=self.settings.database.path
        )

    async def start(self):
        """Start the orchestrator service."""
        # Connect to Redis
        redis_settings = self.settings.redis
        self.redis_client = await aioredis.from_url(
            f"redis://{redis_settings.host}:{redis_settings.port}/{redis_settings.db}",
            password=redis_settings.password if redis_settings.password else None,
            encoding="utf-8",
            decode_responses=True
        )

        # Subscribe to race analysis channel
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe("race:ready_for_analysis")

        print(f"✓ Agent Orchestrator Service started")
        print(f"  Listening for races to analyze...")

        # Start listening loop
        await self.listen_loop()

    async def listen_loop(self):
        """Listen for races to analyze."""
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await self.process_race(data)
                except Exception as e:
                    print(f"✗ Error processing message: {e}")

    async def process_race(self, data: dict):
        """Process a race with both agents."""
        race_url = data["race_url"]
        race_data = data["race_data"]

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing race:")
        print(f"  {race_data['race_info']['location']} R{race_data['race_info']['race_number']}")
        print(f"  URL: {race_url}")

        # Run both agents
        if self.settings.agents.parallel_execution:
            # Parallel execution
            print(f"  Running agents in parallel...")
            results = await asyncio.gather(
                self.run_agent(self.gemini_agent, race_data),
                self.run_agent(self.grok_agent, race_data),
                return_exceptions=True
            )

            gemini_result, grok_result = results
        else:
            # Sequential execution
            print(f"  Running agents sequentially...")
            gemini_result = await self.run_agent(self.gemini_agent, race_data)
            grok_result = await self.run_agent(self.grok_agent, race_data)

        # Save predictions
        predictions_saved = []

        if not isinstance(gemini_result, Exception) and gemini_result:
            pred_id = await self.save_prediction(
                "gemini",
                race_data,
                gemini_result
            )
            predictions_saved.append(("Gemini", pred_id))
            print(f"  ✓ Gemini prediction saved (ID: {pred_id})")
        else:
            print(f"  ✗ Gemini failed: {gemini_result}")

        if not isinstance(grok_result, Exception) and grok_result:
            pred_id = await self.save_prediction(
                "grok",
                race_data,
                grok_result
            )
            predictions_saved.append(("Grok", pred_id))
            print(f"  ✓ Grok prediction saved (ID: {pred_id})")
        else:
            print(f"  ✗ Grok failed: {grok_result}")

        # Publish predictions to Telegram service
        if predictions_saved:
            await self.publish_predictions(race_url, predictions_saved)
            print(f"  ✓ Published {len(predictions_saved)} predictions to Telegram")

    async def run_agent(self, agent, race_data: dict):
        """Run a single agent on race data."""
        try:
            print(f"    → {agent.agent_name.capitalize()} analyzing...")
            structured_bet = await agent.analyze_race(race_data)

            # Validate confidence threshold
            if structured_bet.confidence_score < self.settings.betting.min_confidence_to_bet:
                print(f"    ⚠ {agent.agent_name.capitalize()} confidence too low: "
                      f"{structured_bet.confidence_score:.2f}")
                return None

            print(f"    ✓ {agent.agent_name.capitalize()} complete "
                  f"(confidence: {structured_bet.confidence_score:.2f})")
            return structured_bet

        except Exception as e:
            print(f"    ✗ {agent.agent_name.capitalize()} error: {e}")
            return e

    async def save_prediction(
        self,
        agent_name: str,
        race_data: dict,
        structured_bet
    ) -> int:
        """Save prediction to database."""
        race_info = race_data["race_info"]

        # For now, use 0 as race_id (we'll improve this later)
        # In production, you'd look up or create the race_id from races table
        race_id = 0

        prediction_id = self.prediction_repo.save_prediction(
            agent_name=agent_name,
            race_id=race_id,
            structured_bet=structured_bet,
            race_start_time=race_info.get("start_time_iso")
        )

        return prediction_id

    async def publish_predictions(self, race_url: str, predictions: list[tuple[str, int]]):
        """Publish new predictions to Telegram service."""
        message = {
            "race_url": race_url,
            "predictions": [
                {"agent_name": name, "prediction_id": pred_id}
                for name, pred_id in predictions
            ],
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.redis_client.publish(
            "predictions:new",
            json.dumps(message)
        )

    async def shutdown(self):
        """Shutdown the service."""
        if self.pubsub:
            await self.pubsub.unsubscribe("race:ready_for_analysis")
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        print("\n✓ Orchestrator service stopped")


async def main():
    """Main entry point."""
    service = AgentOrchestratorService()
    try:
        await service.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
