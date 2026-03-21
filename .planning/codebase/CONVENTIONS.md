# Coding Conventions

**Analysis Date:** 2026-03-22

## Naming Patterns

**Files:**
- Module files: `snake_case.py` (e.g., `tabtouch_parser.py`, `logging_config.py`)
- Service entry points: `main.py` in service directories (e.g., `services/monitor/main.py`, `services/orchestrator/main.py`)
- Agent implementations: descriptive names with `_agent.py` suffix (e.g., `gemini_agent.py`, `grok_agent.py`, `base.py`)
- Repository/data access: descriptive names with `_agent.py` or descriptive module name (e.g., `repositories.py`, `migrations.py`)
- Configuration: `settings.py`, `logging_config.py`

**Functions:**
- snake_case throughout (e.g., `parse_race_time()`, `get_next_races()`, `ensure_utc_aware()`)
- Private/internal functions: `_prefixed_name()` (e.g., `_build_workflow()`, `_web_search()`)
- Async functions: same convention but declared with `async def` (e.g., `async def start()`, `async def analyze_race()`)
- Methods and properties follow snake_case (e.g., `self.agent_name`, `self.redis_client`)

**Variables:**
- snake_case for all variables (e.g., `race_data`, `search_results`, `redis_client`)
- Constants: UPPER_SNAKE_CASE (e.g., `SOURCE_TIMEZONE`, `CLIENT_TIMEZONE`, `RACE_CACHE_TTL`)
- Private/internal: leading underscore (e.g., `_race_cache`, `_race_detail_cache`, `_digest_races`)
- Type hints: used throughout for function parameters and return values

**Types:**
- PascalCase for classes (e.g., `BaseRaceAgent`, `GeminiAgent`, `GrokAgent`, `TabTouchParser`, `WinBet`, `PlaceBet`)
- TypedDict for state objects (e.g., `AgentState` with typed fields)
- Pydantic BaseModel for data validation (e.g., `WinBet`, `PlaceBet`, `ExactaBet`, structured bet models)
- Dataclass for data containers (e.g., `RaceResearchContext`, `SearchResult`, `ResearchResult`)

## Code Style

**Formatting:**
- No explicit formatter configured (no .prettierrc or similar)
- Follows Python PEP 8 conventions implicitly
- Line length: implicit, appears to be flexible (some lines >88 chars)
- Indentation: 4 spaces throughout
- Blank lines: single blank line between methods, double blank lines between class definitions

**Linting:**
- No explicit linter configured (no .eslintrc, ruff.toml, or pylint config)
- Type hints are mandatory in function signatures
- All async functions are properly declared with `async def`
- Context managers used appropriately (`async with`, `with`)

**Docstrings:**
- Module-level docstrings: present in all files, triple-quote format
- Function docstrings: Present in key functions, Google-style with Args/Returns sections
- Example from `base.py`:
  ```python
  def _build_workflow(self) -> StateGraph:
      """Build the LangGraph workflow."""
  ```
- Example from `tabtouch_parser.py`:
  ```python
  def parse_race_time(time_str: str, date_str: str = None) -> datetime:
      """
      Parse race time from TabTouch (always in Perth timezone)

      Args:
          time_str: Time string like "05:12", "5:12 AM", "46m", "6m 42s"
          date_str: Optional date string like "Sun 26 Jan"

      Returns:
          Timezone-aware datetime in SOURCE_TIMEZONE
      """
  ```

## Import Organization

**Order:**
1. Standard library imports (e.g., `import asyncio`, `import json`, `import sys`)
2. Third-party imports (e.g., `from pydantic import`, `from langchain_core import`)
3. Local/relative imports (e.g., `from ..config.settings import`, `from ..models.bets import`)

**Path Aliases:**
- Relative imports used consistently: `from ..config.settings`, `from ..models.bets`, `from ..database.repositories`
- System path manipulation when needed (services): `sys.path.insert(0, str(Path(__file__).parent.parent.parent))`
- Type hints with TYPE_CHECKING guard for circular dependencies: `if TYPE_CHECKING: from .research_agent import RaceResearchContext`

**Pattern from `base.py`:**
```python
import json
from typing import Any, Dict, Optional, TypedDict, TYPE_CHECKING

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from ..config.settings import get_settings
from ..models.bets import StructuredBetOutput
from ..web_search import WebResearcher

if TYPE_CHECKING:
    from .research_agent import RaceResearchContext
```

## Error Handling

**Patterns:**
- Try/except with specific exception types where possible
- Wrap external API calls (LLM, TabTouch scraper) in try/except blocks
- Use `exc_info=True` when logging exceptions: `logger.error(f"Error: {e}", exc_info=True)`
- Exponential backoff for retries in result checks (configured in settings)
- Graceful degradation: services log errors and continue rather than crashing
- ValueError raised for validation failures (e.g., API key not configured)

**Example from `services/monitor/main.py`:**
```python
try:
    next_races = await self.check_races()
    await self._maybe_publish_digest(next_races)
except Exception as e:
    logger.error(f"Error in monitor loop: {e}", exc_info=True)

# Wait before next check
await asyncio.sleep(self.settings.timing.monitor_poll_interval)
```

**Example from `src/agents/base.py`:**
```python
openrouter_key = settings.api_keys.openrouter_api_key.get_secret_value()
if not openrouter_key:
    raise ValueError("OPENROUTER_API_KEY not configured")
```

## Logging

**Framework:** Python's built-in `logging` module

**Setup:**
- Centralized configuration in `src/logging_config.py`
- Custom `ServiceFormatter` adds timestamps, log levels, and service context
- Services initialize logger at module level: `logger = setup_logging("service_name")`
- Service names: `"monitor"`, `"orchestrator"`, `"results"`, `"telegram"`

**Patterns:**
- Info level for startup messages: `logger.info(f"🚀 Service Started v{version}")`
- Error level with full traceback for failures: `logger.error(f"Message: {e}", exc_info=True)`
- Warning level for non-critical issues: `logger.warning(f"Received naive datetime: {dt}")`
- Log format: `[TIMESTAMP] [LEVEL] [SERVICE] Message`

**Usage:**
```python
from src.logging_config import setup_logging
logger = setup_logging("service_name")

logger.info("Starting service")
logger.error("Error occurred", exc_info=True)
logger.warning("Warning condition")
```

## Comments

**When to Comment:**
- Complex timezone handling (explicit comments about Perth/UTC conversions)
- Non-obvious regex patterns (e.g., race time parsing patterns in `tabtouch_parser.py`)
- Algorithm choices and trade-offs (e.g., research mode selection)
- External API/format documentation (e.g., Telegram callback data 64-byte limit)

**JSDoc/Docstring Style:**
- Module-level docstrings required in all .py files
- Function docstrings with Args/Returns for public functions
- Inline comments for complex logic

## Async Programming

**Patterns:**
- All I/O operations use async/await (Playwright, Redis, HTTP)
- Services use `async with` for resource management
- Context managers: `async with parser:`, `async with self.parser:`
- Message listening loops: `async for message in pubsub.listen():`
- Concurrent execution: `asyncio.gather()` for parallel agent execution

**Example from `services/orchestrator/main.py`:**
```python
async def listen_loop(self):
    """Listen for races to analyze."""
    async for message in self.pubsub.listen():
        if message["type"] == "message":
            # Process message
```

## Function Design

**Size:**
- Average function: 15-50 lines
- Complex workflows: 100+ lines with clear sections
- Methods delegated to private methods (e.g., `_generate_search_queries()`, `_web_search()`, `_deep_analysis()`)

**Parameters:**
- Use keyword arguments for clarity on complex functions
- Pydantic models and TypedDict for structured parameters
- Type hints mandatory (e.g., `race_data: dict[str, Any]`)
- Optional parameters with defaults and `Optional` type hint

**Return Values:**
- Explicit types: `-> str`, `-> dict`, `-> Optional[int]`
- Return early pattern for error handling
- None used for missing values, not False

## Module Design

**Exports:**
- No explicit `__all__` lists
- All public classes/functions available for import
- Private functions prefixed with `_` but still importable

**Barrel Files:**
- Empty `__init__.py` files in package directories (`src/models/__init__.py`, `src/agents/__init__.py`)
- No re-exports in __init__.py files
- Direct imports used: `from src.agents.gemini_agent import GeminiAgent`

**Layered Architecture:**
- `src/config/` - Configuration and settings
- `src/models/` - Data models and validation
- `src/agents/` - AI agent implementations
- `src/database/` - Data access layer and repositories
- `src/web_search/` - Web search implementation
- `src/logging_config.py` - Logging setup
- `services/` - Microservices (monitor, orchestrator, results, telegram)
- Root level: `tabtouch_parser.py` (scraper), test scripts

## Configuration

**Settings Pattern:**
- Pydantic BaseSettings for environment variables
- Nested configuration classes (e.g., `TimingSettings`, `GeminiAgentSettings`, `GrokAgentSettings`)
- SecretStr for sensitive values (API keys, tokens)
- Fields with Field() for defaults and descriptions
- Validators using `field_validator` decorator

**Example from `src/config/settings.py`:**
```python
class TimingSettings(BaseSettings):
    """Timing configuration for race monitoring and analysis."""

    minutes_before_race: int = Field(
        default=3,
        description="Trigger AI analysis N minutes before race starts"
    )
```

**Environment Variable Convention:**
- Source timezone: `SOURCE_TIMEZONE` (Australia/Perth)
- Client timezone: `CLIENT_TIMEZONE`
- API keys: `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`
- Database path: `DATABASE_PATH`
- Redis connection: env vars for host, port, db, password

---

*Convention analysis: 2026-03-22*
