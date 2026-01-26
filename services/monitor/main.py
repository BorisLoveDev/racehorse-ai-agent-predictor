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
from src.config.settings import get_settings


class RaceMonitorService:
    """Service for monitoring races and triggering analysis."""

    def __init__(self):
        self.settings = get_settings()
        self.redis_client: aioredis.Redis = None
        self.parser = TabTouchParser(headless=True)
        self.monitored_races: set[str] = set()  # Track races we've already triggered

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

        print(f"✓ Race Monitor Service started")
        print(f"  Checking races every {self.settings.timing.monitor_poll_interval}s")
        print(f"  Triggering analysis {self.settings.timing.minutes_before_race} min before race")

        # Start monitoring loop
        await self.monitor_loop()

    async def monitor_loop(self):
        """Main monitoring loop."""
        async with self.parser:
            while True:
                try:
                    await self.check_races()
                except Exception as e:
                    print(f"✗ Error in monitor loop: {e}")

                # Wait before next check
                await asyncio.sleep(self.settings.timing.monitor_poll_interval)

    async def check_races(self):
        """Check upcoming races and trigger analysis if needed."""
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking horse races...")

        # Get next races - only horse racing (not greyhounds or harness)
        next_races = await self.parser.get_next_races(race_type="races")

        if not next_races:
            print("  No upcoming horse races found")
            return

        print(f"  Found {len(next_races)} upcoming horse races")

        # Check each race
        for race in next_races:
            await self.process_race(race)

    async def process_race(self, race):
        """Process a single race."""
        race_url = race.url

        # Skip if already triggered
        if race_url in self.monitored_races:
            return

        # Check if race is within trigger window
        if not race.time_parsed:
            return

        # Save race start time from the list (fallback if details page doesn't have it)
        race_start_time_fallback = race.time_parsed

        now = datetime.now(race.time_parsed.tzinfo)
        time_until_race = (race.time_parsed - now).total_seconds() / 60  # minutes

        # Trigger window: between N minutes and N+2 minutes before race
        trigger_time = self.settings.timing.minutes_before_race
        trigger_window_start = trigger_time + 2
        trigger_window_end = trigger_time

        if trigger_window_end <= time_until_race <= trigger_window_start:
            print(f"\n  → Triggering analysis for: {race.location} R{race.race_number}")
            print(f"     Race starts in {time_until_race:.1f} minutes")
            print(f"     URL: {race_url}")

            # Get full race details
            try:
                race_details = await self.parser.get_race_details(race_url)

                if race_details and race_details.runners:
                    # Format for AI analysis
                    race_data = self._format_race_data(race_details)

                    # Publish to Redis for orchestrator
                    await self.publish_race_for_analysis(race_url, race_data)

                    # Schedule result check
                    start_time_for_check = race_details.start_time_parsed or race_start_time_fallback
                    if start_time_for_check:
                        await self.schedule_result_check(race_url, start_time_for_check)
                    else:
                        print(f"     ⚠ No start time available, cannot schedule result check")

                    # Mark as monitored
                    self.monitored_races.add(race_url)

                    print(f"     ✓ Published to orchestrator")
                else:
                    print(f"     ✗ No runners found")

            except Exception as e:
                print(f"     ✗ Error: {e}")

        elif time_until_race < trigger_window_end:
            # Race is too soon or already started
            if race_url not in self.monitored_races:
                print(f"  ⚠ Race too soon: {race.location} R{race.race_number} ({time_until_race:.1f} min)")
                self.monitored_races.add(race_url)  # Mark to avoid spam

    def _format_race_data(self, race_details) -> dict:
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
                "start_time_iso": race_details.start_time_parsed.isoformat() if race_details.start_time_parsed else None,
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

    async def shutdown(self):
        """Shutdown the service."""
        if self.redis_client:
            await self.redis_client.close()
        await self.parser.__aexit__(None, None, None)
        print("\n✓ Monitor service stopped")


async def main():
    """Main entry point."""
    service = RaceMonitorService()
    try:
        await service.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
