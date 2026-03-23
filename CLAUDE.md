# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a horse racing betting agent system that:
- Scrapes race data from TabTouch (tabtouch.mobi)
- Monitors live races in real-time
- Uses AI agents (Gemini, Grok) to analyze races and generate betting predictions
- Evaluates prediction outcomes against actual results
- Sends notifications via Telegram

## Architecture

### Microservices (Docker Compose)

The system runs as 5 Docker containers communicating via Redis pub/sub:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Monitor   │────▶│    Redis     │◀────│ Orchestrator│
│  (scraper)  │     │  (pub/sub)   │     │ (AI agents) │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌──────────┐  ┌──────────┐
        │ Results │  │ Telegram │  │ races.db │
        │(checker)│  │  (notify)│  │ (SQLite) │
        └─────────┘  └──────────┘  └──────────┘
```

1. **Monitor** (`services/monitor/main.py`)
   - Polls TabTouch every 60s for upcoming horse races
   - Triggers analysis 3-5 minutes before race start
   - Publishes to `race:ready_for_analysis` and `race:schedule_result_check`

2. **Orchestrator** (`services/orchestrator/main.py`)
   - Listens on `race:ready_for_analysis`
   - Runs Gemini and Grok agents in parallel
   - Saves predictions to database
   - Publishes to `predictions:new`

3. **Results** (`services/results/main.py`)
   - Listens on `race:schedule_result_check`
   - Waits for races to finish, fetches results
   - Evaluates predictions against actual finishing order
   - Saves outcomes to `prediction_outcomes` table

4. **Telegram** (`services/telegram/main.py`)
   - Listens on `predictions:new`, `results:evaluated`, `races:digest`
   - Interactive inline keyboards: race browser, bot control, stats period selector
   - `callbacks.py` — CallbackData classes (all ≤ 64 bytes per Telegram limit)
   - `keyboards.py` — keyboard builder functions

5. **Redis** - Message broker for pub/sub communication

### Core Components

1. **TabTouchParser** (`tabtouch_parser.py`)
   - Web scraper using Playwright for async browser automation
   - Methods: `get_next_races()`, `get_race_details()`, `get_race_results()`
   - Handles timezone conversions (SOURCE_TIMEZONE: Australia/Perth)

2. **AI Agents** (`src/agents/`)
   - `ResearchAgent` - Gathers data FIRST, shares with betting agents
   - `GeminiAgent` - Rigorous analysis via google/gemini-3-flash-preview
   - `GrokAgent` - Creative insight via x-ai/grok-4.1-fast
   - Both return `StructuredBet` with win/place/exacta/trifecta/quinella/first4/qps bets

   **Optimized Settings (per multi-model analysis):**
   | Agent | Reasoning | Max Tokens | Web Search | Cost/M |
   |-------|-----------|------------|------------|--------|
   | Research | medium (50%) | 2,000 | Enabled | ~$3 |
   | Gemini | high (80%) | 10,000 | Disabled | ~$3 |
   | Grok | high (80%) | 12,000 | Disabled | ~$0.50 |

   Betting agents don't need web search - research agent gathers data first.

3. **Database** (`src/database/`)
   - `migrations.py` - Schema setup for agents, predictions, outcomes
   - `repositories.py` - Data access layer for predictions and outcomes

4. **Models** (`src/models/`)
   - `StructuredBet` - Betting recommendation with confidence score
   - Various bet types: WinBet, PlaceBet, ExactaBet, etc.

5. **Web Search** (`src/web_search/`)
   - `DuckDuckGoSearch` - Async search via HTML endpoint (replaces Tavily)
   - `SiteVisitor` - Extracts content from web pages
   - `WebResearcher` - Main interface with two modes:
     - **basic**: Fast single-pass search returning snippets
     - **deep**: Multi-agent research with decomposition and synthesis

## Running the System

### Quick Start (Docker)

```bash
# Build base image (required first time or after code changes)
docker build -f Dockerfile.base -t racehorse-base:latest .

# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Production Deployment (Coolify on Meridian)

The system runs in production on **Meridian server** (46.30.43.46, 2 vCPU, 4GB RAM, Ubuntu 24.04) via **Coolify** self-hosted PaaS.

**Coolify identifiers:**
- App UUID: `y8k408og84488csc4gss4gws`
- Project UUID: `kw84s04sos8084840oks84og`
- Build pack: `dockercompose` (reads `docker-compose.yml` from repo)
- Git: `BorisLoveDev/racehorse-ai-agent-predictor`, branch `main`
- 6 containers: redis, searxng, monitor, orchestrator, results, telegram
- 49 env vars configured in Coolify UI

**Deploy via Coolify API (preferred):**
```bash
# Trigger deploy of latest main branch
# Use Coolify MCP tool: mcp__coolify__deploy(tag_or_uuid="y8k408og84488csc4gss4gws")

# Check deployment status
# Use: mcp__coolify__deployment(action="get", uuid="<deployment_uuid>")

# Diagnose app health
# Use: mcp__coolify__diagnose_app(query="racehorse")
```

**Deploy via SSH (fallback):**
```bash
ssh meridian "cd /data/coolify && docker compose up -d"
```

**OOM warning:** 4GB RAM server. Docker `--no-cache` builds with Playwright/Chromium can OOM-kill the server. Avoid force-rebuild when possible. If server becomes unresponsive during build, reboot via Hetzner panel. Typical build time: **8-10 minutes**.

### Development Scripts

```bash
# Activate virtual environment
source venv/bin/activate

# Show next races
python show_next_races.py

# Show race details
python show_race_details.py

# Test AI agents on a specific race
python test_agent.py --url "https://www.tabtouch.mobi/..." --agent both
```

### Environment Variables

Key `.env` variables:
- `SOURCE_TIMEZONE=Australia/Perth` (TabTouch timezone, don't change)
- `CLIENT_TIMEZONE=Asia/Kuala_Lumpur` (user's local timezone)
- `OPENROUTER_API_KEY=...` (required for AI agents)
- `TELEGRAM_BOT_TOKEN=...` (for notifications)
- `TELEGRAM_CHAT_ID=...` (target chat for notifications)

Web search configuration:
- `RACEHORSE_WEB_SEARCH__MODE=basic` ("basic" or "deep")
- `RACEHORSE_WEB_SEARCH__ENABLED=true`
- `RACEHORSE_WEB_SEARCH__MAX_RESULTS_PER_QUERY=3`

## Database Schema

SQLite database `races.db` contains:

- **agents** - AI agent configurations (gemini, grok)
- **predictions** - Generated betting predictions with structured bets
- **prediction_outcomes** - Evaluated results (win/loss, payouts, P/L)
  - Per-bet columns: `win_result`, `place_result`, `exacta_result`, `quinella_result`, `trifecta_result`, `first4_result`, `qps_result` (1/0/NULL)
  - Per-bet payouts: `win_payout`, `place_payout`, `exacta_payout`, `quinella_payout`, `trifecta_payout`, `first4_payout`, `qps_payout`
- **agent_statistics** - Aggregate performance metrics

## Redis Pub/Sub Channels

| Channel | Publisher | Subscriber | Payload |
|---------|-----------|------------|---------|
| `race:ready_for_analysis` | Monitor | Orchestrator | race_url, race_data |
| `race:schedule_result_check` | Monitor | Results | race_url, check_time |
| `predictions:new` | Orchestrator | Telegram | race_url, predictions |
| `results:evaluated` | Results | Telegram | race_url, outcomes |
| `races:digest` | Monitor | Telegram | races list (manual mode only, 10-min throttle) |

## Timing Configuration

Configured in `src/config/settings.py`:

- `monitor_poll_interval`: 60s (check for new races)
- `minutes_before_race`: 3 (trigger analysis window start)
- `result_wait_minutes`: 15 (wait after race start before checking results)
- `result_retry_interval`: 120s (retry if results not available)
- `result_max_retries`: 5

## Web Search Modes

SearXNG is the primary search engine (container `racehorse-searxng`, port 8080 internal).
Fallback: DuckDuckGo (no API key required).

### Modes (`WebResearcher` in `src/web_search/research_modes.py`)

| Mode | Cost | Speed | Description |
|------|------|-------|-------------|
| `off` | $0 | — | No search |
| `raw` | $0 | ~1s | Search → return snippets (no LLM) |
| `lite` | ~$0.01 | ~10-15s | Search → Relevance → visit sites → Extraction → Summary |
| `deep` | ~$0.05-0.10 | ~30-60s | Complexity → Decompose → multi-query → visit → Judge loop |

### External Access (clawdbot)

SearXNG port `8888` is exposed externally for **clawdbot** (AI agent on separate server):
- **Endpoint**: `http://46.30.43.46:8888/search?q=QUERY&format=json`
- **Healthcheck**: `http://46.30.43.46:8888/healthz`
- **Access restricted** by iptables DOCKER-USER chain to `95.142.41.188` only
- **iptables persistence**: systemd `iptables-restore.service` loads `/etc/iptables/rules.v4` on boot
- Clawdbot gets **raw mode** only (SearXNG JSON API); lite/deep require internal LLM agents

To update allowed IPs:
```bash
ssh meridian
iptables -I DOCKER-USER -p tcp --dport 8080 -s <NEW_IP> -j ACCEPT
iptables-save > /etc/iptables/rules.v4
```

## Bot Control (Redis Keys)

| Key | Values | Default | Effect |
|-----|--------|---------|--------|
| `bot:enabled` | `"1"` / `"0"` | `"1"` | Pause/resume — `"0"` skips all scraping |
| `bot:mode` | `"auto"` / `"manual"` | `"auto"` | Auto-analyzes all; manual requires user selection |
| `bot:manual_races` | Redis set of URLs | empty | URLs selected via Telegram for analysis |
| `bot:last_digest_time` | ISO timestamp | unset | TTL key throttling digest to 1 per 10 min |

Set via Telegram `/menu` inline buttons or directly:
```bash
docker compose exec redis redis-cli SET bot:enabled 0
docker compose exec redis redis-cli SET bot:mode manual
```

## aiogram Notes (Telegram service)

- `CallbackData` import: `from aiogram.filters.callback_data import CallbackData`
- `InlineKeyboardBuilder` import: `from aiogram.utils.keyboard import InlineKeyboardBuilder`
- Telegram enforces **64-byte max** on callback data — use short prefixes (`m:`, `r:`, `s:`, `c:`)
- Syntax-check without starting services: `python -c "import ast; ast.parse(open('file.py').read())"`

## Dividend Data Structures

TabTouch `_parse_dividends()` returns different types per bet:
- `dividends["win"]` → `float` (e.g., `3.60`)
- `dividends["place"]` → `list[float]` ordered by finishing position (e.g., `[1.65, 1.90, 2.05]`)
- `dividends["exacta"]` etc. → `{"combination": "1-3", "amount": 18.50}` (dict, NOT float)

When calculating payouts from exotic dividends, always extract `.get("amount", 0)` — never multiply dict directly.

## Key Implementation Notes

- Race times are parsed in SOURCE_TIMEZONE (Perth), stored as UTC
- Monitor uses `race.time_parsed` as fallback when `race_details.start_time_parsed` is None
- AI agents run in parallel via `asyncio.gather()` for speed
- Predictions include confidence scores; bets only placed above threshold (0.5)
- All services are stateless; state lives in Redis and SQLite
- Web search results are cached (5 min TTL) to avoid duplicate queries

## ⚠️ MANDATORY: Verification After Code Changes

**ALWAYS run verification tests after significant code changes (bug fixes, new features, refactoring):**

```bash
# 1. Rebuild base image
docker build -f Dockerfile.base -t racehorse-base:latest .

# 2. Restart services
docker compose down && docker compose up -d

# 3. Run verification script
./verify_fixes.sh

# 4. Monitor logs for errors
docker compose logs -f | grep -i "error\|critical\|warning"

# 5. Check service health
docker compose ps
docker stats --no-stream

# 6. Verify database integrity
sqlite3 races.db "SELECT COUNT(*) FROM predictions"
sqlite3 races.db "SELECT COUNT(*) FROM predictions WHERE race_start_time IS NULL"

# 7. Check Redis state
docker compose exec redis redis-cli KEYS "*"
docker compose exec redis redis-cli SMEMBERS monitor:analyzed_races
```

**Why this is critical:**
- Prevents production bugs from silent failures
- Validates data integrity (timezones, race times, dividends)
- Confirms resource cleanup (browser leaks, Redis state)
- Ensures services communicate correctly (Redis pub/sub)

**When to verify:**
- After bug fixes (ALWAYS)
- After dependency updates
- After configuration changes
- Before deploying to production
- After 24-hour soak test

See `BUGFIX_SUMMARY.md` for detailed verification procedures.

---

## Troubleshooting

**Services not receiving messages:**
- Check Redis is healthy: `docker compose logs redis`
- Verify pub/sub channels with: `docker compose exec redis redis-cli MONITOR`

**No predictions being created:**
- Check orchestrator logs for API errors
- Verify `OPENROUTER_API_KEY` is set in `.env`

**Results not being evaluated:**
- Monitor must send `race:schedule_result_check` (check for time parsing errors)
- Results service checks at `race_start_time + result_wait_minutes`

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Stake Horse Racing Advisor Bot**

A Telegram-driven AI betting advisor for horse racing on Stake.com. The user pastes raw page text from Stake.com directly into the bot, and the system runs it through a multi-step analysis pipeline: parsing odds → web research → AI analysis → bankroll-aware bet sizing → results tracking → reflective learning. Built as a new branch/service in the existing racehorse-agent repo, sharing infrastructure (OpenRouter, SearXNG, Telegram bot token, SQLite, Docker on Meridian).

**Core Value:** Given raw Stake.com race data, produce mathematically sound bet recommendations — sized relative to bankroll — or advise to skip when the odds are squeezed.

### Constraints

- **Tech Stack**: Python 3.13+, aiogram, OpenRouter API, SQLite, Docker — consistent with existing repo
- **Deployment**: Meridian server (2 vCPU, 4GB RAM) — no heavy ML models locally
- **Cost**: Per-race analysis cost should stay under existing agent cost profile (~$0.05–0.10)
- **Single user**: No auth required, single chat ID in env
- **Branch isolation**: New `stake-advisor` branch — no changes to existing services
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11+ - All backend services, scrapers, and AI agents
- Python 3.13 - Tested on development host
- None - monolithic Python codebase
## Runtime
- Docker 27+ with Docker Compose for containerized deployment
- Python 3.11-slim base image in production containers
- pip (Python package manager)
- Lockfile: Not detected (requirements.txt used without hash lock)
## Frameworks
- Playwright 1.40.0+ - Async browser automation for web scraping TabTouch
- Pydantic 2.5.0+ - Data validation and settings management
- Pydantic Settings 2.1.0+ - Environment-based configuration with nested delimiter support
- LangChain 0.1.0+ - Framework for LLM applications and agent workflows
- LangChain OpenAI 0.0.5+ - OpenRouter integration through ChatOpenAI
- LangChain Community 0.0.20+ - Community integrations and utilities
- Langgraph 0.0.20+ - Graph-based workflow orchestration for agents (two-step analysis + bet generation)
- aiohttp 3.9.0+ - Async HTTP client for API calls and web scraping
- asyncio-redis 0.16.0+ - Legacy async Redis support (overlaps with redis package)
- aiogram 3.4.0+ - Telegram bot framework with callback data and inline keyboards
- Telegram Bot API - HTTP-based communication with Telegram service
- BeautifulSoup4 4.12.0+ - HTML parsing for web scraping
- lxml 5.0.0+ - XML/HTML parser backend for BeautifulSoup
- SQLite3 - Built-in Python, file-based SQL database at `races.db`
- Redis 7-alpine (Docker) - In-memory pub/sub message broker (redis:// protocol)
- nest-asyncio 1.6.0+ - Allows nested event loop execution (for REPL testing)
- matplotlib 3.8.0+ - Chart generation for performance statistics
## Key Dependencies
- LangChain (0.1.0+) - LLM framework binding agents, web search, and structured output together
- Playwright (1.40.0+) - Browser automation for scraping TabTouch (Chromium required)
- Pydantic (2.5.0+) - Serialization/deserialization of race data and betting recommendations
- aiogram (3.4.0+) - Telegram bot API abstraction layer
- redis (5.0.0+) - async Redis for pub/sub messaging between services
- aiohttp (3.9.0+) - All HTTP requests (web search, API calls)
- BeautifulSoup4 (4.12.0+) - HTML content extraction from websites
## Configuration
- Pydantic Settings with `env_prefix="RACEHORSE_"` and `env_nested_delimiter="__"`
- Load from `.env` file first, environment variables override
- Hierarchical structure: `RACEHORSE_AGENTS__GEMINI__MAX_TOKENS=10000`
- `RACEHORSE_TIMING__*` - Race monitoring intervals and result check timing
- `RACEHORSE_BETTING__*` - Bet thresholds and exotic bet enablement
- `RACEHORSE_AGENTS__*` - Model IDs, reasoning effort, temperature, token limits
- `RACEHORSE_API_KEYS__*` - OpenRouter and Telegram credentials (SecretStr type)
- `RACEHORSE_REDIS__*` - Redis host/port/password
- `RACEHORSE_DATABASE__PATH` - SQLite database file path
- `RACEHORSE_WEB_SEARCH__*` - Search engine mode (searxng/duckduckgo), URLs, cache settings
- `SOURCE_TIMEZONE` - TabTouch timezone (Australia/Perth, hardcoded in logic)
- `CLIENT_TIMEZONE` - User display timezone (Asia/Kuala_Lumpur default)
- `Dockerfile` - Multi-target: base, monitor, orchestrator, results, telegram
- `Dockerfile.base` - Reusable base image with Playwright browsers pre-installed
- `docker-compose.yml` - 6 services: redis, searxng, monitor, orchestrator, results, telegram
- `.dockerignore` - Standard exclusions
- `entrypoint.sh` - Migration runner before service startup
## Platform Requirements
- macOS host with Miniforge/conda (per CLAUDE.md)
- Python 3.13.12 tested
- Virtual environment: `source venv/bin/activate`
- Playwright browsers auto-installed on first use or in Docker build
- Coolify self-hosted PaaS on Meridian server (2 vCPU, 4GB RAM, Ubuntu 24.04)
- Docker Compose orchestration via Coolify buildpack (`dockercompose`)
- Health checks on Redis and SearXNG (HTTP GET /healthz)
- Volumes: `redis_data`, `db_data`, `race_data`, `searxng_data`
- Network: bridge mode (`racehorse-network`)
- Coolify reads `docker-compose.yml` from git (`BorisLoveDev/racehorse-ai-agent-predictor` main branch)
- Build via Coolify API: `mcp__coolify__deploy(tag_or_uuid="y8k408og84488csc4gss4gws")`
- SSH fallback: `ssh meridian "cd /data/coolify && docker compose up -d"`
- Docker image build requires 8-10 minutes (Playwright Chromium binary inclusion)
- 4GB RAM server: `--no-cache` builds can trigger OOM-kill (use `docker build` with cache if possible)
- Base image reuse: Dockerfile.base cached once, each service target adds only CMD
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module files: `snake_case.py` (e.g., `tabtouch_parser.py`, `logging_config.py`)
- Service entry points: `main.py` in service directories (e.g., `services/monitor/main.py`, `services/orchestrator/main.py`)
- Agent implementations: descriptive names with `_agent.py` suffix (e.g., `gemini_agent.py`, `grok_agent.py`, `base.py`)
- Repository/data access: descriptive names with `_agent.py` or descriptive module name (e.g., `repositories.py`, `migrations.py`)
- Configuration: `settings.py`, `logging_config.py`
- snake_case throughout (e.g., `parse_race_time()`, `get_next_races()`, `ensure_utc_aware()`)
- Private/internal functions: `_prefixed_name()` (e.g., `_build_workflow()`, `_web_search()`)
- Async functions: same convention but declared with `async def` (e.g., `async def start()`, `async def analyze_race()`)
- Methods and properties follow snake_case (e.g., `self.agent_name`, `self.redis_client`)
- snake_case for all variables (e.g., `race_data`, `search_results`, `redis_client`)
- Constants: UPPER_SNAKE_CASE (e.g., `SOURCE_TIMEZONE`, `CLIENT_TIMEZONE`, `RACE_CACHE_TTL`)
- Private/internal: leading underscore (e.g., `_race_cache`, `_race_detail_cache`, `_digest_races`)
- Type hints: used throughout for function parameters and return values
- PascalCase for classes (e.g., `BaseRaceAgent`, `GeminiAgent`, `GrokAgent`, `TabTouchParser`, `WinBet`, `PlaceBet`)
- TypedDict for state objects (e.g., `AgentState` with typed fields)
- Pydantic BaseModel for data validation (e.g., `WinBet`, `PlaceBet`, `ExactaBet`, structured bet models)
- Dataclass for data containers (e.g., `RaceResearchContext`, `SearchResult`, `ResearchResult`)
## Code Style
- No explicit formatter configured (no .prettierrc or similar)
- Follows Python PEP 8 conventions implicitly
- Line length: implicit, appears to be flexible (some lines >88 chars)
- Indentation: 4 spaces throughout
- Blank lines: single blank line between methods, double blank lines between class definitions
- No explicit linter configured (no .eslintrc, ruff.toml, or pylint config)
- Type hints are mandatory in function signatures
- All async functions are properly declared with `async def`
- Context managers used appropriately (`async with`, `with`)
- Module-level docstrings: present in all files, triple-quote format
- Function docstrings: Present in key functions, Google-style with Args/Returns sections
- Example from `base.py`:
- Example from `tabtouch_parser.py`:
## Import Organization
- Relative imports used consistently: `from ..config.settings`, `from ..models.bets`, `from ..database.repositories`
- System path manipulation when needed (services): `sys.path.insert(0, str(Path(__file__).parent.parent.parent))`
- Type hints with TYPE_CHECKING guard for circular dependencies: `if TYPE_CHECKING: from .research_agent import RaceResearchContext`
## Error Handling
- Try/except with specific exception types where possible
- Wrap external API calls (LLM, TabTouch scraper) in try/except blocks
- Use `exc_info=True` when logging exceptions: `logger.error(f"Error: {e}", exc_info=True)`
- Exponential backoff for retries in result checks (configured in settings)
- Graceful degradation: services log errors and continue rather than crashing
- ValueError raised for validation failures (e.g., API key not configured)
## Logging
- Centralized configuration in `src/logging_config.py`
- Custom `ServiceFormatter` adds timestamps, log levels, and service context
- Services initialize logger at module level: `logger = setup_logging("service_name")`
- Service names: `"monitor"`, `"orchestrator"`, `"results"`, `"telegram"`
- Info level for startup messages: `logger.info(f"🚀 Service Started v{version}")`
- Error level with full traceback for failures: `logger.error(f"Message: {e}", exc_info=True)`
- Warning level for non-critical issues: `logger.warning(f"Received naive datetime: {dt}")`
- Log format: `[TIMESTAMP] [LEVEL] [SERVICE] Message`
## Comments
- Complex timezone handling (explicit comments about Perth/UTC conversions)
- Non-obvious regex patterns (e.g., race time parsing patterns in `tabtouch_parser.py`)
- Algorithm choices and trade-offs (e.g., research mode selection)
- External API/format documentation (e.g., Telegram callback data 64-byte limit)
- Module-level docstrings required in all .py files
- Function docstrings with Args/Returns for public functions
- Inline comments for complex logic
## Async Programming
- All I/O operations use async/await (Playwright, Redis, HTTP)
- Services use `async with` for resource management
- Context managers: `async with parser:`, `async with self.parser:`
- Message listening loops: `async for message in pubsub.listen():`
- Concurrent execution: `asyncio.gather()` for parallel agent execution
## Function Design
- Average function: 15-50 lines
- Complex workflows: 100+ lines with clear sections
- Methods delegated to private methods (e.g., `_generate_search_queries()`, `_web_search()`, `_deep_analysis()`)
- Use keyword arguments for clarity on complex functions
- Pydantic models and TypedDict for structured parameters
- Type hints mandatory (e.g., `race_data: dict[str, Any]`)
- Optional parameters with defaults and `Optional` type hint
- Explicit types: `-> str`, `-> dict`, `-> Optional[int]`
- Return early pattern for error handling
- None used for missing values, not False
## Module Design
- No explicit `__all__` lists
- All public classes/functions available for import
- Private functions prefixed with `_` but still importable
- Empty `__init__.py` files in package directories (`src/models/__init__.py`, `src/agents/__init__.py`)
- No re-exports in __init__.py files
- Direct imports used: `from src.agents.gemini_agent import GeminiAgent`
- `src/config/` - Configuration and settings
- `src/models/` - Data models and validation
- `src/agents/` - AI agent implementations
- `src/database/` - Data access layer and repositories
- `src/web_search/` - Web search implementation
- `src/logging_config.py` - Logging setup
- `services/` - Microservices (monitor, orchestrator, results, telegram)
- Root level: `tabtouch_parser.py` (scraper), test scripts
## Configuration
- Pydantic BaseSettings for environment variables
- Nested configuration classes (e.g., `TimingSettings`, `GeminiAgentSettings`, `GrokAgentSettings`)
- SecretStr for sensitive values (API keys, tokens)
- Fields with Field() for defaults and descriptions
- Validators using `field_validator` decorator
- Source timezone: `SOURCE_TIMEZONE` (Australia/Perth)
- Client timezone: `CLIENT_TIMEZONE`
- API keys: `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`
- Database path: `DATABASE_PATH`
- Redis connection: env vars for host, port, db, password
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Five independent services communicating via Redis pub/sub
- Each service handles single responsibility (monitor, analysis, results, notifications)
- Shared database (SQLite) for persistence; Redis for temporary state and messaging
- Async/await throughout for non-blocking I/O
- Stateless services (state in Redis and database only)
## Layers
- Purpose: Scrape and monitor race data from TabTouch
- Location: `tabtouch_parser.py`, `services/monitor/main.py`
- Contains: Web scraper using Playwright, race timing/scheduling logic
- Depends on: TabTouch website (via Playwright), Redis for pub/sub
- Used by: Monitor service exclusively
- Purpose: Generate betting predictions using multiple AI agents
- Location: `src/agents/`, `services/orchestrator/main.py`
- Contains: Research agent, Gemini agent, Grok agent, base agent implementations
- Depends on: OpenRouter API, web search (SearXNG/DuckDuckGo), LangChain/LangGraph
- Used by: Orchestrator service (triggered by Redis messages)
- Purpose: Track race results and evaluate prediction accuracy
- Location: `services/results/main.py`, `src/database/repositories.py`
- Contains: Result checking, outcome evaluation, statistics calculation
- Depends on: TabTouchParser, SQLite database, prediction data
- Used by: Results service (scheduled via Redis)
- Purpose: Send predictions and results to Telegram with interactive controls
- Location: `services/telegram/main.py`, `services/telegram/callbacks.py`, `services/telegram/keyboards.py`
- Contains: Telegram bot logic, inline keyboards, callback handlers, analytics charts
- Depends on: aiogram library, database repositories, Redis for bot state
- Used by: Telegram service (consuming Redis messages)
- Purpose: Configuration, database access, logging, web search
- Location: `src/config/`, `src/database/`, `src/logging_config.py`, `src/web_search/`
- Contains: Settings management, repositories, logging, search engine abstractions
- Depends on: Pydantic (settings), SQLite (database), LLM providers (OpenRouter)
- Used by: All services
## Data Flow
- **Transient state (Redis):** `bot:enabled`, `bot:mode`, `bot:manual_races`, analyzed race URLs (24h TTL)
- **Persistent state (SQLite):** Predictions, outcomes, agent statistics, agent configs
- **Message bus (Redis pub/sub):** 5 channels for service communication
## Key Abstractions
- Purpose: Unified interface for web scraping and race data extraction
- Examples: `tabtouch_parser.py`
- Pattern: Context manager (async with parser) for browser lifecycle, timezone-aware datetime handling
- Purpose: Encapsulate LLM interaction and structured output generation
- Examples: `src/agents/base.py`, `src/agents/gemini_agent.py`, `src/agents/grok_agent.py`, `src/agents/research_agent.py`
- Pattern: Base class with state machine (LangGraph), two-step workflow (research + analysis), research context sharing
- Purpose: Multi-mode web search abstraction
- Examples: `src/web_search/research_modes.py`, `src/web_search/searxng.py`, `src/web_search/duckduckgo.py`
- Pattern: Strategy pattern for search engines (SearXNG vs DuckDuckGo), mode-based behavior (raw, lite, deep)
- Purpose: Data access layer with clean query interfaces
- Examples: `src/database/repositories.py`
- Pattern: Repository pattern for predictions, outcomes, agents, statistics
- Purpose: Type-safe bet representation with validation
- Examples: `src/models/bets.py` (WinBet, PlaceBet, ExactaBet, TrifectaBet, QuinellaBet, etc.)
- Pattern: Pydantic BaseModel with field validators, JSON serialization
## Entry Points
- Location: `services/monitor/main.py`
- Triggers: Docker start (continuous loop)
- Responsibilities: Poll TabTouch every 60s, detect upcoming races, publish analysis requests
- Location: `services/orchestrator/main.py`
- Triggers: Redis message on `race:ready_for_analysis` channel
- Responsibilities: Run research and betting agents, persist predictions
- Location: `services/results/main.py`
- Triggers: Redis message on `race:schedule_result_check` channel
- Responsibilities: Poll for race results, evaluate predictions, update statistics
- Location: `services/telegram/main.py`
- Triggers: Redis messages on `predictions:new`, `results:evaluated`, `races:digest`
- Responsibilities: Format and send notifications, handle user interactions (commands, callbacks)
- `test_agent.py` - Test single race with both agents
- `show_next_races.py` - Show upcoming races (debugging)
- `show_race_details.py` - Show detailed race info (debugging)
## Error Handling
- External API failures (OpenRouter, TabTouch) are logged and don't crash services
- Database locks are retried with exponential backoff
- Invalid race data is skipped; service continues monitoring
- Missing predictions don't block results evaluation (evaluate what we have)
- Telegram rate limiting (20 msg/sec) via async queue
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
