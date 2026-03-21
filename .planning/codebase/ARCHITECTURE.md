# Architecture

**Analysis Date:** 2026-03-22

## Pattern Overview

**Overall:** Microservices Event-Driven Architecture

**Key Characteristics:**
- Five independent services communicating via Redis pub/sub
- Each service handles single responsibility (monitor, analysis, results, notifications)
- Shared database (SQLite) for persistence; Redis for temporary state and messaging
- Async/await throughout for non-blocking I/O
- Stateless services (state in Redis and database only)

## Layers

**Data Collection Layer:**
- Purpose: Scrape and monitor race data from TabTouch
- Location: `tabtouch_parser.py`, `services/monitor/main.py`
- Contains: Web scraper using Playwright, race timing/scheduling logic
- Depends on: TabTouch website (via Playwright), Redis for pub/sub
- Used by: Monitor service exclusively

**Analysis Layer (AI):**
- Purpose: Generate betting predictions using multiple AI agents
- Location: `src/agents/`, `services/orchestrator/main.py`
- Contains: Research agent, Gemini agent, Grok agent, base agent implementations
- Depends on: OpenRouter API, web search (SearXNG/DuckDuckGo), LangChain/LangGraph
- Used by: Orchestrator service (triggered by Redis messages)

**Evaluation Layer:**
- Purpose: Track race results and evaluate prediction accuracy
- Location: `services/results/main.py`, `src/database/repositories.py`
- Contains: Result checking, outcome evaluation, statistics calculation
- Depends on: TabTouchParser, SQLite database, prediction data
- Used by: Results service (scheduled via Redis)

**Notification Layer:**
- Purpose: Send predictions and results to Telegram with interactive controls
- Location: `services/telegram/main.py`, `services/telegram/callbacks.py`, `services/telegram/keyboards.py`
- Contains: Telegram bot logic, inline keyboards, callback handlers, analytics charts
- Depends on: aiogram library, database repositories, Redis for bot state
- Used by: Telegram service (consuming Redis messages)

**Infrastructure Layer:**
- Purpose: Configuration, database access, logging, web search
- Location: `src/config/`, `src/database/`, `src/logging_config.py`, `src/web_search/`
- Contains: Settings management, repositories, logging, search engine abstractions
- Depends on: Pydantic (settings), SQLite (database), LLM providers (OpenRouter)
- Used by: All services

## Data Flow

**Race Analysis Pipeline:**

1. **Monitor detects upcoming race** (every 60s)
   - Calls `TabTouchParser.get_next_races()`
   - Identifies races within trigger window (3-5 min before start)

2. **Publish analysis request**
   - Publishes to `race:ready_for_analysis` channel with race_url and race_data
   - Also publishes to `race:schedule_result_check` for timing

3. **Orchestrator receives and analyzes**
   - Subscribes to `race:ready_for_analysis`
   - Runs ResearchAgent first (generates search queries, fetches context)
   - Runs GeminiAgent and GrokAgent in parallel (with shared research context)
   - Stores predictions in SQLite `predictions` table

4. **Publish predictions**
   - Publishes to `predictions:new` with prediction data and race URL
   - Telegram service receives and formats for display

5. **Results evaluation (asynchronous)**
   - Subscribes to `race:schedule_result_check`
   - Waits for `race_start_time + result_wait_minutes` (15 min)
   - Fetches actual results from TabTouch
   - Compares against predictions, calculates payouts
   - Stores outcomes in `prediction_outcomes` table
   - Publishes to `results:evaluated`

6. **Telegram notifications**
   - Receives `predictions:new` → formats and sends betting advice
   - Receives `results:evaluated` → sends outcome summary
   - Manual mode: sends digest of upcoming races every 10 minutes (throttled)

**State Management:**
- **Transient state (Redis):** `bot:enabled`, `bot:mode`, `bot:manual_races`, analyzed race URLs (24h TTL)
- **Persistent state (SQLite):** Predictions, outcomes, agent statistics, agent configs
- **Message bus (Redis pub/sub):** 5 channels for service communication

## Key Abstractions

**TabTouchParser:**
- Purpose: Unified interface for web scraping and race data extraction
- Examples: `tabtouch_parser.py`
- Pattern: Context manager (async with parser) for browser lifecycle, timezone-aware datetime handling

**AI Agents:**
- Purpose: Encapsulate LLM interaction and structured output generation
- Examples: `src/agents/base.py`, `src/agents/gemini_agent.py`, `src/agents/grok_agent.py`, `src/agents/research_agent.py`
- Pattern: Base class with state machine (LangGraph), two-step workflow (research + analysis), research context sharing

**WebResearcher:**
- Purpose: Multi-mode web search abstraction
- Examples: `src/web_search/research_modes.py`, `src/web_search/searxng.py`, `src/web_search/duckduckgo.py`
- Pattern: Strategy pattern for search engines (SearXNG vs DuckDuckGo), mode-based behavior (raw, lite, deep)

**Repositories:**
- Purpose: Data access layer with clean query interfaces
- Examples: `src/database/repositories.py`
- Pattern: Repository pattern for predictions, outcomes, agents, statistics

**Models:**
- Purpose: Type-safe bet representation with validation
- Examples: `src/models/bets.py` (WinBet, PlaceBet, ExactaBet, TrifectaBet, QuinellaBet, etc.)
- Pattern: Pydantic BaseModel with field validators, JSON serialization

## Entry Points

**Monitor Service:**
- Location: `services/monitor/main.py`
- Triggers: Docker start (continuous loop)
- Responsibilities: Poll TabTouch every 60s, detect upcoming races, publish analysis requests

**Orchestrator Service:**
- Location: `services/orchestrator/main.py`
- Triggers: Redis message on `race:ready_for_analysis` channel
- Responsibilities: Run research and betting agents, persist predictions

**Results Service:**
- Location: `services/results/main.py`
- Triggers: Redis message on `race:schedule_result_check` channel
- Responsibilities: Poll for race results, evaluate predictions, update statistics

**Telegram Service:**
- Location: `services/telegram/main.py`
- Triggers: Redis messages on `predictions:new`, `results:evaluated`, `races:digest`
- Responsibilities: Format and send notifications, handle user interactions (commands, callbacks)

**Development Scripts:**
- `test_agent.py` - Test single race with both agents
- `show_next_races.py` - Show upcoming races (debugging)
- `show_race_details.py` - Show detailed race info (debugging)

## Error Handling

**Strategy:** Graceful degradation with logging

**Patterns:**
- External API failures (OpenRouter, TabTouch) are logged and don't crash services
- Database locks are retried with exponential backoff
- Invalid race data is skipped; service continues monitoring
- Missing predictions don't block results evaluation (evaluate what we have)
- Telegram rate limiting (20 msg/sec) via async queue

## Cross-Cutting Concerns

**Logging:** Centralized `ServiceFormatter` in `src/logging_config.py`. All services use `setup_logging(service_name)` for consistent output.

**Validation:** Pydantic models in `src/models/` validate all structured data (bets, configurations). Validators enforce business rules (e.g., horse numbers 1-30).

**Authentication:** API keys stored in `.env`, loaded via Pydantic `SecretStr` fields in `src/config/settings.py`. Never logged.

**Timezone Handling:** All races parsed in SOURCE_TIMEZONE (Australia/Perth), stored as UTC in database. `TabTouchParser` handles conversions; results service normalizes all datetimes to UTC.

**Configuration:** Environment variables mapped to Pydantic settings in `src/config/settings.py`. Supports nested configs (redis, database, agents, web_search).

---

*Architecture analysis: 2026-03-22*
