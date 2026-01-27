#!/usr/bin/env python3
"""
Pipeline Test Script

Tests the full pipeline flow with mock data via Redis pub/sub.
This allows testing without waiting for real races.

Usage:
    python scripts/test_pipeline.py [--timeout 60] [--skip-telegram]

Requires:
    - Redis running (localhost:6379 or via docker)
    - Services running (orchestrator, results) or use --mock-services
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import redis.asyncio as aioredis

# Load fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def load_mock_race_data() -> dict:
    """Load mock race data from fixture."""
    with open(FIXTURES_DIR / "mock_race_data.json") as f:
        return json.load(f)


def load_mock_results() -> dict:
    """Load mock results from fixture."""
    with open(FIXTURES_DIR / "mock_results.json") as f:
        return json.load(f)


class PipelineTester:
    """Test the full pipeline with mock data."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis_client: aioredis.Redis = None
        self.pubsub = None
        self.received_events = []

    async def connect(self):
        """Connect to Redis."""
        self.redis_client = await aioredis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        print(f"[OK] Connected to Redis")

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.pubsub:
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()

    async def subscribe_to_events(self):
        """Subscribe to all pipeline channels."""
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe(
            "race:ready_for_analysis",
            "race:schedule_result_check",
            "predictions:new",
            "results:evaluated"
        )
        print("[OK] Subscribed to pipeline channels")

    async def listen_for_events(self, timeout: float = 30.0):
        """Listen for events with timeout."""
        try:
            async with asyncio.timeout(timeout):
                async for message in self.pubsub.listen():
                    if message["type"] == "message":
                        event = {
                            "channel": message["channel"],
                            "data": json.loads(message["data"]),
                            "timestamp": datetime.now().isoformat()
                        }
                        self.received_events.append(event)
                        print(f"  [EVENT] {event['channel']}")
                        yield event
        except asyncio.TimeoutError:
            print(f"  [TIMEOUT] No more events after {timeout}s")

    async def publish_mock_race(self) -> str:
        """Publish mock race data to trigger orchestrator."""
        race_data = load_mock_race_data()

        # Update timestamps to be current
        now = datetime.utcnow()
        race_data["race_info"]["start_time_iso"] = (
            now + timedelta(minutes=5)
        ).isoformat() + "Z"

        race_url = race_data["race_info"]["url"]

        message = {
            "race_url": race_url,
            "race_data": race_data,
            "timestamp": now.isoformat()
        }

        await self.redis_client.publish(
            "race:ready_for_analysis",
            json.dumps(message)
        )

        print(f"[OK] Published mock race to race:ready_for_analysis")
        print(f"     URL: {race_url}")

        return race_url

    async def publish_mock_result_check(self, race_url: str):
        """Publish mock result check to trigger results service."""
        check_time = datetime.utcnow() - timedelta(seconds=10)  # Past time triggers immediate check

        message = {
            "race_url": race_url,
            "check_time": check_time.isoformat(),
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.redis_client.publish(
            "race:schedule_result_check",
            json.dumps(message)
        )

        print(f"[OK] Published result check to race:schedule_result_check")

    async def test_redis_connectivity(self) -> bool:
        """Test Redis connectivity."""
        try:
            pong = await self.redis_client.ping()
            print(f"[OK] Redis ping: {pong}")
            return True
        except Exception as e:
            print(f"[FAIL] Redis connectivity: {e}")
            return False

    async def test_orchestrator_response(self, timeout: float = 60.0) -> bool:
        """Test that orchestrator responds to race:ready_for_analysis."""
        print("\n=== Testing Orchestrator ===")

        race_url = await self.publish_mock_race()

        # Wait for predictions:new event
        print("Waiting for predictions:new event...")

        received_prediction = False
        async for event in self.listen_for_events(timeout):
            if event["channel"] == "predictions:new":
                data = event["data"]
                predictions = data.get("predictions", [])
                print(f"[OK] Received predictions: {len(predictions)} agents responded")
                for pred in predictions:
                    print(f"     - {pred['agent_name']}: prediction_id={pred['prediction_id']}")
                received_prediction = True
                break

        if not received_prediction:
            print("[FAIL] No predictions received from orchestrator")
            return False

        return True

    async def test_full_pipeline(self, timeout: float = 120.0) -> dict:
        """Test the full pipeline from race to results."""
        print("\n=== Testing Full Pipeline ===")

        results = {
            "redis_connected": False,
            "race_published": False,
            "predictions_received": False,
            "results_evaluated": False,
            "events": []
        }

        # Test Redis
        results["redis_connected"] = await self.test_redis_connectivity()
        if not results["redis_connected"]:
            return results

        # Subscribe to events
        await self.subscribe_to_events()

        # Publish mock race
        race_url = await self.publish_mock_race()
        results["race_published"] = True

        # Wait for events
        print("\nWaiting for pipeline events...")
        async for event in self.listen_for_events(timeout):
            results["events"].append(event["channel"])

            if event["channel"] == "predictions:new":
                results["predictions_received"] = True
                print("[OK] Predictions received")

            elif event["channel"] == "results:evaluated":
                results["results_evaluated"] = True
                print("[OK] Results evaluated")
                break

        return results

    def print_summary(self, results: dict):
        """Print test summary."""
        print("\n" + "=" * 50)
        print("PIPELINE TEST SUMMARY")
        print("=" * 50)

        checks = [
            ("Redis Connected", results.get("redis_connected", False)),
            ("Race Published", results.get("race_published", False)),
            ("Predictions Received", results.get("predictions_received", False)),
            ("Results Evaluated", results.get("results_evaluated", False)),
        ]

        all_passed = True
        for name, passed in checks:
            status = "PASS" if passed else "FAIL"
            symbol = "✓" if passed else "✗"
            print(f"  {symbol} {name}: {status}")
            if not passed:
                all_passed = False

        print("=" * 50)
        if all_passed:
            print("ALL TESTS PASSED")
        else:
            print("SOME TESTS FAILED")
            print("\nTroubleshooting:")
            print("  1. Ensure Redis is running: docker compose up redis -d")
            print("  2. Ensure services are running: docker compose up -d")
            print("  3. Check service logs: docker compose logs orchestrator")

        return all_passed


async def main():
    parser = argparse.ArgumentParser(description="Test the racehorse agent pipeline")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for waiting for events (default: 120)"
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379/0",
        help="Redis URL (default: redis://localhost:6379/0)"
    )
    parser.add_argument(
        "--orchestrator-only",
        action="store_true",
        help="Only test orchestrator (don't wait for results)"
    )

    args = parser.parse_args()

    print("=" * 50)
    print("RACEHORSE AGENT PIPELINE TEST")
    print("=" * 50)
    print(f"Redis URL: {args.redis_url}")
    print(f"Timeout: {args.timeout}s")
    print()

    tester = PipelineTester(redis_url=args.redis_url)

    try:
        await tester.connect()

        if args.orchestrator_only:
            success = await tester.test_orchestrator_response(timeout=args.timeout)
            sys.exit(0 if success else 1)
        else:
            results = await tester.test_full_pipeline(timeout=args.timeout)
            success = tester.print_summary(results)
            sys.exit(0 if success else 1)

    except ConnectionRefusedError:
        print("[FAIL] Cannot connect to Redis. Is it running?")
        print("  Start Redis: docker compose up redis -d")
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
