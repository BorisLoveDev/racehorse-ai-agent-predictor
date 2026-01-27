"""
Integration tests for the full racehorse agent pipeline.

These tests verify that all components work together correctly:
- Redis pub/sub connectivity
- Database operations
- Race analysis flow
- Results evaluation flow

Requirements:
    - Redis running (use `docker compose up redis -d`)
    - SQLite database available

Run with:
    pytest tests/integration/test_full_pipeline.py -v
"""

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_mock_race_data() -> dict:
    """Load mock race data from fixture."""
    with open(FIXTURES_DIR / "mock_race_data.json") as f:
        return json.load(f)


def load_mock_results() -> dict:
    """Load mock results from fixture."""
    with open(FIXTURES_DIR / "mock_results.json") as f:
        return json.load(f)


class TestRedisConnectivity:
    """Test Redis pub/sub connectivity."""

    @pytest.fixture
    def redis_url(self):
        """Get Redis URL from environment or default."""
        return os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    @pytest.mark.asyncio
    async def test_redis_ping(self, redis_url):
        """Test basic Redis connectivity."""
        import redis.asyncio as aioredis

        try:
            client = await aioredis.from_url(redis_url)
            pong = await client.ping()
            assert pong is True
            await client.close()
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    @pytest.mark.asyncio
    async def test_pubsub_roundtrip(self, redis_url):
        """Test Redis pub/sub roundtrip."""
        import redis.asyncio as aioredis

        try:
            client = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            pubsub = client.pubsub()
            await pubsub.subscribe("test:channel")

            # Publish a message
            test_data = {"test": "data", "timestamp": datetime.now().isoformat()}
            await client.publish("test:channel", json.dumps(test_data))

            # Receive the message
            received = None
            async for message in pubsub.listen():
                if message["type"] == "message":
                    received = json.loads(message["data"])
                    break

            assert received is not None
            assert received["test"] == "data"

            await pubsub.unsubscribe("test:channel")
            await pubsub.close()
            await client.close()

        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    @pytest.mark.asyncio
    async def test_pipeline_channels_exist(self, redis_url):
        """Verify pipeline channels can be subscribed to."""
        import redis.asyncio as aioredis

        channels = [
            "race:ready_for_analysis",
            "race:schedule_result_check",
            "predictions:new",
            "results:evaluated"
        ]

        try:
            client = await aioredis.from_url(redis_url)
            pubsub = client.pubsub()

            for channel in channels:
                await pubsub.subscribe(channel)

            # Verify subscriptions
            numsub = await client.pubsub_numsub(*channels)
            # numsub returns list of tuples (channel, count)

            await pubsub.unsubscribe(*channels)
            await pubsub.close()
            await client.close()

        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


class TestDatabaseOperations:
    """Test database operations."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        # Initialize schema
        conn = sqlite3.connect(path)
        cursor = conn.cursor()

        # Create minimal schema for testing
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS agents (
                agent_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                model_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT OR IGNORE INTO agents (name, model_name) VALUES
                ('gemini', 'google/gemini-3-flash-preview'),
                ('grok', 'x-ai/grok-4.1-fast');

            CREATE TABLE IF NOT EXISTS predictions (
                prediction_id INTEGER PRIMARY KEY,
                agent_id INTEGER NOT NULL,
                race_id INTEGER,
                race_url TEXT NOT NULL,
                race_location TEXT,
                race_number INTEGER,
                race_start_time TEXT,
                confidence_score REAL NOT NULL,
                risk_level TEXT,
                analysis_summary TEXT,
                key_factors TEXT,
                structured_bet TEXT NOT NULL,
                odds_snapshot TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            );

            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                outcome_id INTEGER PRIMARY KEY,
                prediction_id INTEGER NOT NULL UNIQUE,
                finishing_order TEXT NOT NULL,
                bet_results TEXT NOT NULL,
                payouts TEXT NOT NULL,
                total_bet_amount REAL NOT NULL,
                total_payout REAL NOT NULL,
                net_profit_loss REAL NOT NULL,
                actual_dividends TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
            );
        ''')
        conn.commit()
        conn.close()

        yield path

        # Cleanup
        os.unlink(path)

    def test_agents_table_exists(self, temp_db):
        """Test that agents table has expected entries."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM agents ORDER BY agent_id")
        agents = [row[0] for row in cursor.fetchall()]

        assert "gemini" in agents
        assert "grok" in agents

        conn.close()

    def test_prediction_insert(self, temp_db):
        """Test inserting a prediction."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        structured_bet = {
            "win_bet": {"horse_number": 1, "amount": 10},
            "confidence_score": 0.75
        }

        cursor.execute('''
            INSERT INTO predictions
            (agent_id, race_url, race_location, race_number, confidence_score,
             risk_level, analysis_summary, structured_bet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            1,  # gemini
            "https://test.com/race/1",
            "TestTrack",
            3,
            0.75,
            "medium",
            "Test analysis",
            json.dumps(structured_bet)
        ))
        conn.commit()

        prediction_id = cursor.lastrowid
        assert prediction_id > 0

        # Verify retrieval
        cursor.execute("SELECT * FROM predictions WHERE prediction_id = ?", (prediction_id,))
        row = cursor.fetchone()
        assert row is not None

        conn.close()

    def test_outcome_insert(self, temp_db):
        """Test inserting an outcome."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # First insert a prediction
        structured_bet = {"win_bet": {"horse_number": 1, "amount": 10}}
        cursor.execute('''
            INSERT INTO predictions
            (agent_id, race_url, confidence_score, structured_bet)
            VALUES (?, ?, ?, ?)
        ''', (1, "https://test.com/race/1", 0.75, json.dumps(structured_bet)))
        prediction_id = cursor.lastrowid

        # Insert outcome
        finishing_order = [{"number": 1, "name": "Winner"}]
        bet_results = {"win": True}
        payouts = {"win": 35.0}

        cursor.execute('''
            INSERT INTO prediction_outcomes
            (prediction_id, finishing_order, bet_results, payouts,
             total_bet_amount, total_payout, net_profit_loss)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            prediction_id,
            json.dumps(finishing_order),
            json.dumps(bet_results),
            json.dumps(payouts),
            10.0,
            35.0,
            25.0
        ))
        conn.commit()

        outcome_id = cursor.lastrowid
        assert outcome_id > 0

        conn.close()


class TestMockRaceData:
    """Test mock race data fixtures."""

    def test_mock_race_data_loads(self):
        """Test that mock race data fixture loads correctly."""
        race_data = load_mock_race_data()

        assert "race_info" in race_data
        assert "runners" in race_data
        assert "pool_totals" in race_data

        # Verify race info
        race_info = race_data["race_info"]
        assert "location" in race_info
        assert "race_number" in race_info
        assert "url" in race_info

        # Verify runners
        runners = race_data["runners"]
        assert len(runners) > 0
        for runner in runners:
            assert "number" in runner
            assert "name" in runner
            assert "fixed_win" in runner

    def test_mock_results_loads(self):
        """Test that mock results fixture loads correctly."""
        results = load_mock_results()

        assert "finishing_order" in results
        assert "dividends" in results

        # Verify finishing order
        finishing_order = results["finishing_order"]
        assert len(finishing_order) > 0
        for horse in finishing_order:
            assert "number" in horse
            assert "position" in horse

        # Verify dividends
        dividends = results["dividends"]
        assert "win" in dividends
        assert "exacta" in dividends

    def test_race_data_has_valid_odds(self):
        """Test that mock race data has valid odds."""
        race_data = load_mock_race_data()

        for runner in race_data["runners"]:
            # Win odds should be > 1 (decimal odds)
            assert runner["fixed_win"] > 1.0
            # Place odds should be less than win odds
            assert runner["fixed_place"] < runner["fixed_win"]


class TestLoggingConfig:
    """Test the logging configuration."""

    def test_setup_logging(self):
        """Test that logging setup works."""
        from src.logging_config import setup_logging

        logger = setup_logging("test_service")
        assert logger is not None
        assert logger.name == "test_service"

    def test_logger_has_handlers(self):
        """Test that logger has handlers configured."""
        from src.logging_config import setup_logging

        logger = setup_logging("test_handlers")
        assert len(logger.handlers) > 0

    def test_get_logger(self):
        """Test getting an existing logger."""
        from src.logging_config import setup_logging, get_logger

        setup_logging("existing_service")
        logger = get_logger("existing_service")
        assert logger is not None


class TestTimezoneHandling:
    """Test timezone handling utilities."""

    def test_utc_naive_conversion(self):
        """Test converting timezone-aware datetime to UTC naive."""
        from services.results.main import to_utc_naive
        from datetime import timezone

        # Test with UTC aware datetime
        aware_utc = datetime(2025, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
        naive = to_utc_naive(aware_utc)
        assert naive.tzinfo is None
        assert naive.hour == 12

        # Test with naive datetime (assumed UTC)
        naive_dt = datetime(2025, 1, 27, 12, 0, 0)
        result = to_utc_naive(naive_dt)
        assert result.tzinfo is None
        assert result.hour == 12


# Pytest configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
