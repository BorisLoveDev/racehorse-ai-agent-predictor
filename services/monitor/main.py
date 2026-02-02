"""
Race Monitor Service

Continuously monitors upcoming races and triggers analysis at configured time before race start.
Publishes to Redis for orchestrator service to pick up.
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
from src.config.settings import get_settings, get_version
from src.logging_config import setup_logging

# Initialize logger
logger = setup_logging("monitor")


class RaceMonitorService:
    """Service for monitoring races and triggering analysis."""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: aioredis.Redis = None
        self.parser = TabTouchParser(headless=True)
        # monitored_races now persisted in Redis (no in-memory set)

    async def start(self):
        """Start the monitoring service."""
        # Connect to Redis
        redis_settings = self.settings.redis
        self.redis_client = await aioredis.from_url(
            f"redis://{redis_settings.host}:{redis_settings.port}/{redis_settings.db}",
            password=redis_settings.password if redis_settings.password else None,
            encoding="utf-8",
            decode_responses=True
        )

        logger.info(f"🚀 Race Monitor Service v{get_version()} started")
        logger.info(f"Checking races every {self.settings.timing.monitor_poll_interval}s")
        logger.info(f"Trigger window: {self.settings.timing.minutes_before_race + 2} min before to 1 min after race start")

        # Start monitoring loop
        await self.monitor_loop()

    async def _is_monitored(self, race_url: str) -> bool:
        """Check if race was already analyzed (Redis-backed)."""
        key = "monitor:analyzed_races"
        return await self.redis_client.sismember(key, race_url)

    async def _add_to_monitored(self, race_url: str):
        """Mark race as analyzed (Redis-backed with 24h TTL)."""
        key = "monitor:analyzed_races"
        await self.redis_client.sadd(key, race_url)
        await self.redis_client.expire(key, 86400)  # 24h TTL

    async def monitor_loop(self):
        """Main monitoring loop."""
        async with self.parser:
            while True:
                try:
                    await self.check_races()
                except Exception as e:
                    logger.error(f"Error in monitor loop: {e}", exc_info=True)

                # Wait before next check
                await asyncio.sleep(self.settings.timing.monitor_poll_interval)

    async def check_races(self):
        """Check upcoming races and trigger analysis if needed."""
        logger.info("Checking horse races...")

        # Get next races - only horse racing (not greyhounds or harness)
        next_races = await self.parser.get_next_races(race_type="races")

        if not next_races:
            logger.info("No upcoming horse races found")
            return

        logger.info(f"Found {len(next_races)} upcoming horse races")

        # Check each race
        for race in next_races:
            await self.process_race(race)

    async def process_race(self, race):
        """Process a single race."""
        race_url = race.url

        # Skip if already triggered (Redis-backed check)
        if await self._is_monitored(race_url):
            return

        # Check if race is within trigger window
        if not race.time_parsed:
            return

        # Save race start time from the list (fallback if details page doesn't have it)
        race_start_time_fallback = race.time_parsed

        now = datetime.now(race.time_parsed.tzinfo)
        time_until_race = (race.time_parsed - now).total_seconds() / 60  # minutes

        # Trigger window: from configured minutes before to 30 seconds before race start
        # Prevents useless predictions after race has started
        trigger_window_start = self.settings.timing.minutes_before_race + 2  # add buffer
        trigger_window_end = 0.5   # 30 seconds before (not after!)

        if trigger_window_end <= time_until_race <= trigger_window_start:
            logger.info(f"Triggering analysis | race={race.location} R{race.race_number} | time_until={time_until_race:.1f}min | url={race_url}")

            # Get full race details
            try:
                race_details = await self.parser.get_race_details(race_url)

                if race_details and race_details.runners:
                    # Determine race start time (prefer details, fallback to list time)
                    race_start_time = race_details.start_time_parsed or race_start_time_fallback

                    if not race_start_time:
                        logger.error(f"Cannot determine race start time | race={race.location} R{race.race_number}")
                        return  # Skip this race

                    # Format for AI analysis (includes start_time_iso)
                    race_data = self._format_race_data(race_details, race_start_time)

                    # Publish to Redis for orchestrator
                    await self.publish_race_for_analysis(race_url, race_data)

                    # Schedule result check
                    await self.schedule_result_check(race_url, race_start_time)

                    # Mark as monitored (Redis-backed)
                    await self._add_to_monitored(race_url)

                    logger.info(f"Published to orchestrator | race={race.location} R{race.race_number} | runners={len(race_details.runners)}")
                else:
                    logger.warning(f"No runners found | race={race.location} R{race.race_number} | url={race_url}")

            except Exception as e:
                logger.error(f"Error processing race | race={race.location} R{race.race_number} | error={e}", exc_info=True)

        elif time_until_race < trigger_window_end:
            # Race too close to start time (less than 30 seconds) - too late
            if not await self._is_monitored(race_url):
                logger.warning(f"Race too close to start | race={race.location} R{race.race_number} | time_until={time_until_race:.1f}min")
                await self._add_to_monitored(race_url)  # Mark to avoid spam

    def _format_race_data(self, race_details, race_start_time) -> dict:
        """Format race details for AI analysis."""
        return {
            "race_info": {
                "location": race_details.location,
                "date": race_details.date,
                "race_number": race_details.race_number,
                "race_name": race_details.race_name,
                "distance": race_details.distance,
                "track_condition": race_details.track_condition,
                "race_type": race_details.race_type,
                "start_time": race_details.start_time,
                "start_time_iso": race_start_time.isoformat(),  # Always present (fallback guaranteed)
                "url": race_details.url
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
                    "tote_place": r.tote_place
                }
                for r in race_details.runners
            ],
            "pool_totals": race_details.pool_totals
        }

    async def publish_race_for_analysis(self, race_url: str, race_data: dict):
        """Publish race to Redis for orchestrator service."""
        message = {
            "race_url": race_url,
            "race_data": race_data,
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.redis_client.publish(
            "race:ready_for_analysis",
            json.dumps(message)
        )

    async def schedule_result_check(self, race_url: str, race_start_time: datetime):
        """Schedule result check after race finishes."""
        # Calculate when to check for results (N minutes after race start)
        check_time = race_start_time + timedelta(
            minutes=self.settings.timing.result_wait_minutes
        )

        message = {
            "race_url": race_url,
            "check_time": check_time.isoformat(),
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.redis_client.publish(
            "race:schedule_result_check",
            json.dumps(message)
        )

        logger.info(f"Scheduled result check | url={race_url} | check_at={check_time.strftime('%H:%M:%S')}")

    async def shutdown(self):
        """Shutdown the service."""
        if self.redis_client:
            await self.redis_client.close()
        await self.parser.__aexit__(None, None, None)
        logger.info("Monitor service stopped")


async def main():
    """Main entry point."""
    service = RaceMonitorService()
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
