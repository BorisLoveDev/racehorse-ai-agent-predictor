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
   - `GeminiAgent` - Uses google/gemini-3-flash-preview via OpenRouter
   - `GrokAgent` - Uses x-ai/grok-4.1-fast via OpenRouter
   - Both return `StructuredBet` with win/place/exacta/trifecta/quinella/first4/qps bets

3. **Database** (`src/database/`)
   - `migrations.py` - Schema setup for agents, predictions, outcomes
   - `repositories.py` - Data access layer for predictions and outcomes

4. **Models** (`src/models/`)
   - `StructuredBet` - Betting recommendation with confidence score
   - Various bet types: WinBet, PlaceBet, ExactaBet, etc.

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

## Key Implementation Notes

- Race times are parsed in SOURCE_TIMEZONE (Perth), stored as UTC
- Monitor uses `race.time_parsed` as fallback when `race_details.start_time_parsed` is None
- AI agents run in parallel via `asyncio.gather()` for speed
- Predictions include confidence scores; bets only placed above threshold (0.5)
- All services are stateless; state lives in Redis and SQLite

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
