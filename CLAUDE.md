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
   - Listens on `predictions:new` and `results:evaluated`
   - Sends formatted notifications to configured chat

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
- **agent_statistics** - Aggregate performance metrics

## Redis Pub/Sub Channels

| Channel | Publisher | Subscriber | Payload |
|---------|-----------|------------|---------|
| `race:ready_for_analysis` | Monitor | Orchestrator | race_url, race_data |
| `race:schedule_result_check` | Monitor | Results | race_url, check_time |
| `predictions:new` | Orchestrator | Telegram | race_url, predictions |
| `results:evaluated` | Results | Telegram | race_url, outcomes |

## Timing Configuration

Configured in `src/config/settings.py`:

- `monitor_poll_interval`: 60s (check for new races)
- `minutes_before_race`: 3 (trigger analysis window start)
- `result_wait_minutes`: 15 (wait after race start before checking results)
- `result_retry_interval`: 120s (retry if results not available)
- `result_max_retries`: 5

## Web Search Modes

The system uses DuckDuckGo for web research (no API key required):

### Basic Mode (default)
- Single-pass search returning snippets
- Fast, low latency
- Good for quick context gathering

### Deep Mode
- Multi-agent research loop:
  1. ComplexityAgent determines if query needs decomposition
  2. DecomposeAgent breaks complex queries into sub-queries
  3. Parallel search across all queries
  4. SiteVisitor extracts content from top pages
  5. ExtractionAgent pulls relevant information
  6. SummarizationAgent synthesizes results
  7. JudgeAgent verifies completeness
- Slower but more thorough
- Enable with: `RACEHORSE_WEB_SEARCH__MODE=deep`

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
