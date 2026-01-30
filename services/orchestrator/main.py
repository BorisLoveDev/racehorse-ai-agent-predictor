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
from src.agents.research_agent import ResearchAgent
from src.config.settings import get_settings, get_version
from src.database.repositories import PredictionRepository
from src.logging_config import setup_logging

# Initialize logger
logger = setup_logging("orchestrator")


class AgentOrchestratorService:
    """Service for running AI agents on races."""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: aioredis.Redis = None
        self.pubsub = None

        # Initialize Research Agent (runs first, shares results)
        logger.info("Initializing Research Agent...")
        self.research_agent = ResearchAgent()

        # Initialize Betting Agents
        logger.info("Initializing Betting Agents...")
        self.gemini_agent = GeminiAgent()
        self.grok_agent = GrokAgent()
        logger.info("All agents initialized")

        # Initialize database repository
        self.prediction_repo = PredictionRepository(
            db_path=self.settings.database.path
        )

    async def warmup_agents(self):
        """Warmup agents to verify LLM connectivity."""
        from langchain_core.messages import HumanMessage

        logger.info("Warming up agents...")

        agents = [
            (self.gemini_agent, "Gemini"),
            (self.grok_agent, "Grok")
        ]

        for agent, name in agents:
            try:
                response = await agent.llm.ainvoke([
                    HumanMessage(content="Say 'ready' if you can respond.")
                ])
                response_text = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"  {name}: {response_text[:100]}")
            except Exception as e:
                logger.error(f"  {name} warmup failed: {e}")

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

        logger.info(f"🚀 Agent Orchestrator Service v{get_version()} started")

        # Warmup agents to verify connectivity
        await self.warmup_agents()

        logger.info("Listening for races to analyze...")

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
                    logger.error(f"Error processing message: {e}", exc_info=True)

    async def process_race(self, data: dict):
        """Process a race with both agents."""
        race_url = data["race_url"]
        race_data = data["race_data"]

        race_info = race_data['race_info']
        logger.info(f"Processing race | location={race_info['location']} | race_number=R{race_info['race_number']} | url={race_url}")

        # Step 1: Run Research Agent FIRST (single search for both agents)
        research_context = None
        if self.settings.agents.research.enabled:
            logger.info("Running Research Agent to pre-fetch search results...")
            try:
                research_context = await self.research_agent.research(race_data)
                logger.info(f"Research complete | queries={len(research_context.queries_generated)} | results={len(research_context.search_results)}")
            except Exception as e:
                logger.error(f"Research Agent failed, betting agents will search independently | error={e}")

        # Step 2: Run Betting Agents (with shared research context)
        if self.settings.agents.parallel_execution:
            # Parallel execution
            logger.info("Running betting agents in parallel...")
            results = await asyncio.gather(
                self.run_agent(self.gemini_agent, race_data, research_context),
                self.run_agent(self.grok_agent, race_data, research_context),
                return_exceptions=True
            )

            gemini_result, grok_result = results
        else:
            # Sequential execution
            logger.info("Running betting agents sequentially...")
            gemini_result = await self.run_agent(self.gemini_agent, race_data, research_context)
            grok_result = await self.run_agent(self.grok_agent, race_data, research_context)

        # Save predictions
        predictions_saved = []

        if not isinstance(gemini_result, Exception) and gemini_result:
            pred_id = await self.save_prediction(
                "gemini",
                race_data,
                gemini_result
            )
            predictions_saved.append(("Gemini", pred_id))
            logger.info(f"Gemini prediction saved | prediction_id={pred_id} | confidence={gemini_result.confidence_score:.2f}")
        else:
            logger.error(f"Gemini failed | error={gemini_result}")

        if not isinstance(grok_result, Exception) and grok_result:
            pred_id = await self.save_prediction(
                "grok",
                race_data,
                grok_result
            )
            predictions_saved.append(("Grok", pred_id))
            logger.info(f"Grok prediction saved | prediction_id={pred_id} | confidence={grok_result.confidence_score:.2f}")
        else:
            logger.error(f"Grok failed | error={grok_result}")

        # Publish predictions to Telegram service
        if predictions_saved:
            await self.publish_predictions(race_url, predictions_saved)
            logger.info(f"Published {len(predictions_saved)} predictions to Telegram")

    async def run_agent(self, agent, race_data: dict, research_context=None):
        """Run a single agent on race data."""
        try:
            logger.info(f"Agent analyzing | agent={agent.agent_name}")

            # Use pre-fetched research if available
            if research_context:
                structured_bet = await agent.analyze_race_with_research(race_data, research_context)
            else:
                structured_bet = await agent.analyze_race(race_data)

            # Validate confidence threshold
            if structured_bet.confidence_score < self.settings.betting.min_confidence_to_bet:
                logger.warning(f"Confidence too low | agent={agent.agent_name} | confidence={structured_bet.confidence_score:.2f} | threshold={self.settings.betting.min_confidence_to_bet}")
                return None

            logger.info(f"Agent complete | agent={agent.agent_name} | confidence={structured_bet.confidence_score:.2f}")
            return structured_bet

        except Exception as e:
            logger.error(f"Agent error | agent={agent.agent_name} | error={e}", exc_info=True)
            return e

    def _build_odds_snapshot(self, race_data: dict, structured_bet) -> dict:
        """Extract odds for horses in the bet from race_data."""
        runners = {str(r["number"]): r for r in race_data.get("runners", [])}
        snapshot = {"win": {}, "place": {}}

        # Win bet odds
        if structured_bet.win_bet:
            num = str(structured_bet.win_bet.horse_number)
            if num in runners:
                snapshot["win"][num] = runners[num].get("fixed_win", 0)

        # Place bet odds
        if structured_bet.place_bet:
            num = str(structured_bet.place_bet.horse_number)
            if num in runners:
                snapshot["place"][num] = runners[num].get("fixed_place", 0)

        # Exacta - use win odds as approximation
        if structured_bet.exacta_bet:
            key = f"{structured_bet.exacta_bet.first}-{structured_bet.exacta_bet.second}"
            snapshot["exacta"] = {key: None}

        # Quinella
        if structured_bet.quinella_bet:
            horses = structured_bet.quinella_bet.horses  # already sorted by model validator
            key = f"{horses[0]}-{horses[1]}"
            snapshot["quinella"] = {key: None}

        # Trifecta
        if structured_bet.trifecta_bet:
            key = f"{structured_bet.trifecta_bet.first}-{structured_bet.trifecta_bet.second}-{structured_bet.trifecta_bet.third}"
            snapshot["trifecta"] = {key: None}

        # First 4
        if structured_bet.first4_bet:
            horses = structured_bet.first4_bet.horses  # list of 4 horses in exact order
            key = f"{horses[0]}-{horses[1]}-{horses[2]}-{horses[3]}"
            snapshot["first4"] = {key: None}

        # QPS
        if structured_bet.qps_bet:
            horses = structured_bet.qps_bet.horses  # 2-4 horses, already sorted
            key = "-".join(str(h) for h in horses)
            snapshot["qps"] = {key: None}

        return snapshot

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

        # Extract odds snapshot
        odds_snapshot = self._build_odds_snapshot(race_data, structured_bet)

        # Get race start time - prefer start_time_iso, fallback to current time
        # This is used by Results service to schedule result checks
        race_start_time = race_info.get("start_time_iso")
        if not race_start_time:
            # BUG FIX: Previously used datetime.utcnow() which could cause
            # immediate result checks. Now we log a warning but still use
            # current time as last resort (race is imminent anyway).
            # The Monitor service should always provide start_time_iso from
            # race.time_parsed fallback, so this branch should rarely execute.
            race_start_time = datetime.utcnow().isoformat() + "Z"
            logger.warning(f"Using fallback race_start_time | race={race_info.get('location')} R{race_info.get('race_number')} | fallback_time={race_start_time}")

        prediction_id = self.prediction_repo.save_prediction(
            agent_name=agent_name,
            race_id=race_id,
            structured_bet=structured_bet,
            race_start_time=race_start_time,
            odds_snapshot_json=json.dumps(odds_snapshot)
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
        logger.info("Orchestrator service stopped")


async def main():
    """Main entry point."""
    service = AgentOrchestratorService()
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
