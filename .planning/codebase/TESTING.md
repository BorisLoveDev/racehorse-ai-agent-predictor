# Testing Patterns

**Analysis Date:** 2026-03-22

## Test Framework

**Runner:**
- pytest (via `requirements.txt`)
- Config: No dedicated config file (`pytest.ini`, `pyproject.toml [tool.pytest]`, etc.) -- pytest is invoked directly

**Assertion Library:**
- Standard `assert` statements (pytest native)
- `unittest.mock` for mocking (`AsyncMock`, `MagicMock`, `patch`)

**Async Support:**
- `pytest-asyncio` for async test methods (`@pytest.mark.asyncio`)

**Run Commands:**
```bash
# Activate venv first
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run integration tests only
pytest tests/integration/test_full_pipeline.py -v

# Run with output
pytest tests/ -v -s
```

## Test File Organization

**Location:**
- Separate `tests/` directory at project root (not co-located)

**Naming:**
- Test files: `test_*.py`
- Test classes: `Test*` (e.g., `TestRedisConnectivity`, `TestDatabaseOperations`)
- Test methods: `test_*` (e.g., `test_redis_ping`, `test_prediction_insert`)

**Structure:**
```
tests/
├── __init__.py
├── fixtures/
│   ├── mock_race_data.json    # Sample race data with 6 runners
│   └── mock_results.json      # Sample finishing order and dividends
└── integration/
    ├── __init__.py
    └── test_full_pipeline.py  # All integration tests
```

## Test Structure

**Suite Organization:**
```python
# tests/integration/test_full_pipeline.py

class TestRedisConnectivity:
    """Test Redis pub/sub connectivity."""

    @pytest.fixture
    def redis_url(self):
        """Get Redis URL from environment or default."""
        return os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    @pytest.mark.asyncio
    async def test_redis_ping(self, redis_url):
        """Test basic Redis connectivity."""
        try:
            client = await aioredis.from_url(redis_url)
            pong = await client.ping()
            assert pong is True
            await client.close()
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
```

**Patterns:**
- Group related tests into classes (e.g., `TestRedisConnectivity`, `TestDatabaseOperations`, `TestMockRaceData`)
- Use `pytest.skip()` when external dependencies (Redis) are unavailable -- tests degrade gracefully
- Use `pytest.fixture` for setup/teardown (e.g., `temp_db` creates and destroys temp SQLite)
- Session-scoped `event_loop` fixture for async tests

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**
```python
from unittest.mock import AsyncMock, MagicMock, patch

# AsyncMock for async functions (imported but not heavily used in current tests)
mock_client = AsyncMock()
mock_client.ping.return_value = True
```

**What to Mock:**
- External services (Redis, AI APIs) when testing locally
- Database connections via temp SQLite files (not mocked -- real SQLite used)

**What NOT to Mock:**
- SQLite operations -- use real temp databases via `tempfile.mkstemp()`
- Pydantic model validation -- test with real data structures
- Logging configuration -- test actual setup

## Fixtures and Factories

**Test Data:**
```python
# Load from JSON fixture files
def load_mock_race_data() -> dict:
    """Load mock race data from fixture."""
    with open(FIXTURES_DIR / "mock_race_data.json") as f:
        return json.load(f)

def load_mock_results() -> dict:
    """Load mock results from fixture."""
    with open(FIXTURES_DIR / "mock_results.json") as f:
        return json.load(f)
```

**Location:**
- `tests/fixtures/mock_race_data.json` -- 6 runners with odds, form, jockey, trainer
- `tests/fixtures/mock_results.json` -- finishing order with dividends (win, place, exacta, quinella, trifecta, first4, qps)

**Database Fixture:**
```python
@pytest.fixture
def temp_db(self):
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    # Create minimal schema inline (not using migrations.py)
    cursor.executescript('''...''')
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)  # Cleanup
```

## Coverage

**Requirements:** None enforced -- no coverage configuration or thresholds
**Coverage tool:** Not configured

## Test Types

**Unit Tests:**
- Not present as separate files
- Some unit-level tests exist within `test_full_pipeline.py`:
  - `TestLoggingConfig` -- tests `setup_logging()` from `src/logging_config.py`
  - `TestTimezoneHandling` -- tests `to_utc_naive()` from `services/results/main.py`
  - `TestMockRaceData` -- validates fixture JSON structure and data constraints

**Integration Tests:**
- `tests/integration/test_full_pipeline.py` -- 13 test methods across 5 test classes:
  - `TestRedisConnectivity` -- ping, pub/sub roundtrip, channel subscription
  - `TestDatabaseOperations` -- agents table, prediction insert, outcome insert
  - `TestMockRaceData` -- fixture loading, data validation, odds validation
  - `TestLoggingConfig` -- logger setup, handlers, retrieval
  - `TestTimezoneHandling` -- UTC-aware to naive conversion

**E2E Tests:**
- Not automated. Manual E2E is done via Docker Compose + `verify_fixes.sh`

**Manual Testing (primary approach):**
```bash
# Test scraper against live TabTouch
python show_next_races.py
python show_race_details.py

# Test AI agents on a specific race
python test_agent.py --url "https://www.tabtouch.mobi/..." --agent both
python test_agent.py --url "https://www.tabtouch.mobi/..." --agent gemini
python test_agent.py --url "https://www.tabtouch.mobi/..." --agent grok
```

## Verification Script

**`verify_fixes.sh`** -- Bash script for post-deployment verification:
- Rebuilds Docker base image
- Restarts all services
- Checks service health (5 containers)
- Validates Redis state persistence
- Checks for naive datetime warnings
- Checks for missing `race_start_time` errors
- Monitors memory usage (browser cleanup)
- Validates Telegram rate limiting
- Runs database integrity checks

```bash
# Run full verification suite
./verify_fixes.sh
```

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_pubsub_roundtrip(self, redis_url):
    """Test Redis pub/sub roundtrip."""
    client = await aioredis.from_url(redis_url, ...)
    pubsub = client.pubsub()
    await pubsub.subscribe("test:channel")
    await client.publish("test:channel", json.dumps(test_data))
    async for message in pubsub.listen():
        if message["type"] == "message":
            received = json.loads(message["data"])
            break
    assert received["test"] == "data"
```

**Graceful Skip on Missing Dependencies:**
```python
try:
    client = await aioredis.from_url(redis_url)
    # ... test logic ...
except Exception as e:
    pytest.skip(f"Redis not available: {e}")
```

**Temp Database Pattern:**
```python
def test_prediction_insert(self, temp_db):
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO predictions ...''')
    conn.commit()
    prediction_id = cursor.lastrowid
    assert prediction_id > 0
    conn.close()
```

## Gaps and Recommendations

- No unit tests for core business logic (`src/agents/base.py`, `src/models/bets.py`, `tabtouch_parser.py`)
- No test coverage measurement configured
- Integration test schema is hand-written inline, not using `src/database/migrations.py` (schema drift risk)
- No mocking of OpenRouter API calls for agent testing
- Manual testing via `test_agent.py` is the primary method for AI agent validation
- `verify_fixes.sh` is the closest thing to a CI pipeline but requires Docker running

---

*Testing analysis: 2026-03-22*
